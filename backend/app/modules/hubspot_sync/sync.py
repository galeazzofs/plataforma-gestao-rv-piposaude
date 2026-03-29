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

    # Search gongoed tickets (won + MRR > 0)
    filters = [
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": "closed_won"},
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
                was_created = _process_ticket(client, ticket)
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
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


def _process_ticket(hs_client, ticket):
    """Process a single HubSpot ticket into a policy. Returns True if created."""
    props = ticket.get("properties", {})
    ticket_id = ticket["id"]

    # Map EV by email
    ev_email = props.get("solicitante_demanda", "")
    ev = User.query.filter_by(email=ev_email).first() if ev_email else None

    # Upsert client
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

    # Update fields
    if ev:
        policy.ev_id = ev.id
    if client_obj:
        policy.client_id = client_obj.id
    policy.segment = map_segment(props.get("cotar___segmentacao_pipo"))
    policy.benefit_type = map_benefit_type(props.get("apolice___beneficio"))
    policy.mrr_projected = parse_decimal(props.get("mrr___receita_mensal"))
    policy.closed_date = parse_date(props.get("closed_date"))

    # Fetch deal associations
    try:
        assoc = hs_client.get_associations("tickets", ticket_id, "deals")
        deal_ids = [r["toObjectId"] for r in assoc.get("results", [])]
        if deal_ids:
            policy.deal_id = str(deal_ids[0])
            deal = hs_client.get_deal(deal_ids[0], DEAL_PROPERTIES)
            deal_props = deal.get("properties", {})
            policy.deal_stage = deal_props.get("dealstage")
            policy.deploy_date = parse_date(deal_props.get("hs_v2_date_entered_8438574"))
    except Exception as e:
        logger.warning(f"Deal association fetch failed for ticket {ticket_id}: {e}")

    db.session.flush()
    return is_new
