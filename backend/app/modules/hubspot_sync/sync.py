import logging
from datetime import datetime, timezone
from app.extensions import db
from app.models import User, Policy, Client
from app.models.client import normalize_client_name
from app.modules.hubspot_sync.client import HubSpotClient
from app.modules.hubspot_sync.mapper import (
    map_segment, map_benefit_type, parse_date, parse_decimal,
)

logger = logging.getLogger(__name__)

TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "apolice___beneficio", "cliente___nome_da_empresa",
]

DEAL_PROPERTIES = ["dealstage", "hs_v2_date_entered_8438574"]

TICKET_IMPLANT_PROPERTIES = ["previsao_primeiro_pagamento", "mrr_pos_implantacao"]


def run_sync():
    """Main sync job: pull gongoed tickets from HubSpot, upsert into policies.

    Returns summary dict.
    """
    client = HubSpotClient()
    created = 0
    updated = 0
    errors = []

    # Pre-load owner map (owner_id → email) for EV resolution
    try:
        owner_map = client.get_all_owners()
        logger.info(f"Loaded {len(owner_map)} HubSpot owners")
    except Exception as e:
        logger.warning(f"Could not load owners: {e}")
        owner_map = {}

    # Search gongoed tickets (Placement pipeline → Gongo stage)
    filters = [
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": "11947921"},
    ]

    after = None
    while True:
        try:
            result = client.search_tickets(
                filters=filters,
                properties=TICKET_PROPERTIES,
                after=after,
            )
        except Exception as e:
            logger.error(f"HubSpot search failed: {e}")
            errors.append(f"Search failed: {e}")
            break

        for ticket in result.get("results", []):
            try:
                was_created = _process_ticket(client, ticket, owner_map)
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                db.session.rollback()
                ticket_id = ticket.get("id", "unknown")
                logger.error(f"Error processing ticket {ticket_id}: {e}")
                errors.append(f"Ticket {ticket_id}: {e}")

        # Pagination
        paging = result.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")
        if not after:
            break

    db.session.commit()

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "created": created,
        "updated": updated,
        "errors": errors,
        "error_count": len(errors),
    }
    logger.info(f"HubSpot sync completed: {summary}")
    return summary


def _process_ticket(hs_client, ticket, owner_map=None):
    """Process a single HubSpot ticket into a policy. Returns True if created.

    Respects Policy.is_locked: when set, lockable fields (ev_id, client_id,
    segment, closed_date, first_payment_real, initial_installments_paid,
    partner_operator) are NOT overwritten. Non-lockable fields (mrr_projected,
    benefit_type, deal_*) are always updated.
    """
    owner_map = owner_map or {}
    props = ticket.get("properties", {})
    ticket_id = ticket["id"]

    # Resolve EV: owner_id → email → user OR direct email fallback
    owner_id_or_email = props.get("solicitante_demanda")
    if owner_id_or_email:
        ev_email = owner_map.get(str(owner_id_or_email), owner_id_or_email)
    else:
        ev_email = None
    ev = User.query.filter_by(email=ev_email).first() if ev_email else None

    # Upsert client (we need the client to link, regardless of lock state)
    client_name = props.get("cliente___nome_da_empresa", "")
    client_obj = None
    if client_name:
        client_obj = Client.find_or_create(client_name, ev_id=ev.id if ev else None)
        db.session.flush()

    # Find or create policy
    policy = Policy.query.filter_by(hubspot_ticket_id=str(ticket_id)).first()
    is_new = policy is None
    if is_new:
        policy = Policy(hubspot_ticket_id=str(ticket_id))
        db.session.add(policy)

    locked = bool(getattr(policy, "is_locked", False))

    # Lockable fields — only update if not locked
    if not locked:
        if ev:
            policy.ev_id = ev.id
        if client_obj:
            policy.client_id = client_obj.id
        policy.segment = map_segment(props.get("cotar___segmentacao_pipo"))
        policy.closed_date = parse_date(props.get("closed_date"))

    # Non-lockable fields — always update
    policy.benefit_type = map_benefit_type(props.get("apolice___beneficio"))
    policy.mrr_projected = parse_decimal(props.get("mrr___receita_mensal"))

    # Fetch deal associations (non-lockable — always refresh)
    try:
        assoc = hs_client.get_associations("tickets", ticket_id, "deals")
        deal_ids = [r["toObjectId"] for r in assoc.get("results", [])]
        if deal_ids:
            policy.deal_id = str(deal_ids[0])
            deal = hs_client.get_deal(deal_ids[0], DEAL_PROPERTIES)
            deal_props = deal.get("properties", {})
            policy.deal_stage = deal_props.get("dealstage")
            if not locked:
                # deploy_date from the deal is also considered lockable context
                policy.deploy_date = parse_date(deal_props.get("hs_v2_date_entered_8438574"))
    except Exception as e:
        logger.warning(f"Deal association fetch failed for ticket {ticket_id}: {e}")

    db.session.flush()
    return is_new
