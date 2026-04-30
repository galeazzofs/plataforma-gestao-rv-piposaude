"""HubSpot sync — apolice-anchored.

Orchestrates pulling apolices (deals in pipeline 2453678), validating their
ticket+default-deal linkage, and upserting one row in `policies` per apolice.

See docs/superpowers/specs/2026-04-29-policy-sync-from-apolices-pipeline-design.md
"""
import logging
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import User, Policy, Client, BenefitType, Segment
from app.modules.hubspot_sync.client import HubSpotClient
from app.modules.hubspot_sync.mapper import (
    map_segment, map_benefit_type, parse_date, parse_decimal,
)

logger = logging.getLogger(__name__)

# --- HubSpot pipeline / stage IDs ---
APOLICE_PIPELINE_ID = "2453678"
PLACEMENT_PIPELINE_ID = "651307"
GONGO_STAGE_ID = "11947921"
DEFAULT_DEAL_PIPELINE_ID = "default"  # TBD: confirm slug
GONGO_DATE_FLOOR = date(2024, 9, 1)

VALID_BENEFITS_HUBSPOT = ["Saúde", "Odonto", "Vida", "Saúde e Odonto"]

APOLICE_PROPERTIES = ["apolice___beneficio", "numero_apolice", "parceiro"]
TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "cliente___nome_da_empresa",
    "hs_pipeline", "hs_pipeline_stage",
]
DEAL_VALIDATION_PROPERTIES = ["hs_pipeline"]


def _fetch_apolices(client):
    """Phase 1 — search apolices in the apolice pipeline filtered by benefit.

    Returns list of apolice dicts as returned by HubSpot search
    (each has at least `id` and `properties`).
    """
    filters = [
        {"propertyName": "hs_pipeline", "operator": "EQ", "value": APOLICE_PIPELINE_ID},
        {"propertyName": "apolice___beneficio", "operator": "IN", "values": VALID_BENEFITS_HUBSPOT},
    ]
    apolices = []
    after = None
    while True:
        result = client.search_deals(
            filters=filters,
            properties=APOLICE_PROPERTIES,
            after=after,
        )
        apolices.extend(result.get("results", []))
        next_cursor = result.get("paging", {}).get("next", {}).get("after")
        if not next_cursor:
            break
        after = next_cursor
    logger.info(f"_fetch_apolices: {len(apolices)} apolices found")
    return apolices


def _fetch_apolice_tickets(client, apolices, summary):
    """Phase 2 — batch fetch ticket associations for all apolices.

    Returns dict {apolice_id: first_ticket_id}. Apolices without any ticket
    are skipped (counted in summary["skipped"]["no_ticket"]). When an apolice
    has multiple tickets, takes the first and logs a warning.
    """
    if not apolices:
        return {}
    apolice_ids = [a["id"] for a in apolices]
    associations = client.batch_read_associations("deals", "tickets", apolice_ids)
    out = {}
    for apolice_id in apolice_ids:
        ticket_ids = associations.get(apolice_id, [])
        if not ticket_ids:
            summary["skipped"]["no_ticket"] += 1
            logger.warning(f"Apolice {apolice_id} has no associated ticket — skipped")
            continue
        if len(ticket_ids) > 1:
            logger.warning(
                f"Apolice {apolice_id} has {len(ticket_ids)} associated tickets; "
                f"using first ({ticket_ids[0]})"
            )
        out[apolice_id] = ticket_ids[0]
    logger.info(f"_fetch_apolice_tickets: {len(out)}/{len(apolice_ids)} apolices linked to tickets")
    return out


def _fetch_and_validate_tickets(client, ticket_ids, summary):
    """Phase 3 — batch fetch tickets and filter by pipeline/stage/date.

    `ticket_ids` is an iterable; duplicates are deduped before the API call.
    Returns dict {ticket_id: properties_dict} for tickets that pass all filters.
    Skipped tickets are counted in summary by reason.
    """
    unique_ids = list(set(ticket_ids))
    if not unique_ids:
        return {}
    all_props = client.batch_read_objects("tickets", unique_ids, TICKET_PROPERTIES)
    out = {}
    for ticket_id, props in all_props.items():
        if props.get("hs_pipeline") != PLACEMENT_PIPELINE_ID:
            summary["skipped"]["wrong_pipeline"] += 1
            continue
        if props.get("hs_pipeline_stage") != GONGO_STAGE_ID:
            summary["skipped"]["not_gongo"] += 1
            continue
        closed = parse_date(props.get("closed_date"))
        if closed is None or closed < GONGO_DATE_FLOOR:
            summary["skipped"]["too_old"] += 1
            continue
        out[ticket_id] = props
    logger.info(f"_fetch_and_validate_tickets: {len(out)}/{len(unique_ids)} tickets valid")
    return out


def _upsert_policy(apolice, ticket_props, owner_map, ticket_id=None):
    """Phase 5 — create or update one Policy row from an apolice + its ticket.

    Args:
        apolice: dict from HubSpot search (has `id` and `properties`)
        ticket_props: dict of ticket properties (already validated/filtered)
        owner_map: dict {owner_id_str: email}
        ticket_id: HubSpot ticket id; pulled from caller's apolice→ticket map.
                   Optional for backward-compat in tests but production passes it.

    Returns True if a new row was created, False if updated.
    Respects Policy.is_locked: locked rows keep ev_id, client_id, segment, closed_date.
    """
    apolice_id = apolice["id"]
    apolice_props = apolice.get("properties", {})

    # Resolve EV: solicitante_demanda may be an owner_id (lookup in map) or already an email
    raw_ev = ticket_props.get("solicitante_demanda")
    ev_email = owner_map.get(str(raw_ev), raw_ev) if raw_ev else None
    ev = User.query.filter_by(email=ev_email).first() if ev_email else None

    # Upsert client (always — even when locked we may need it)
    client_name = ticket_props.get("cliente___nome_da_empresa") or ""
    client_obj = None
    if client_name:
        client_obj = Client.find_or_create(client_name, ev_id=ev.id if ev else None)
        db.session.flush()

    # Find or create policy
    policy = Policy.query.filter_by(hubspot_apolice_id=str(apolice_id)).first()
    is_new = policy is None
    if is_new:
        policy = Policy(hubspot_apolice_id=str(apolice_id))
        db.session.add(policy)

    locked = bool(getattr(policy, "is_locked", False))

    # Always update (non-lockable):
    policy.hubspot_ticket_id = str(ticket_id) if ticket_id else policy.hubspot_ticket_id
    policy.numero_apolice = apolice_props.get("numero_apolice") or None
    policy.partner_operator = apolice_props.get("parceiro") or None
    benefit_raw = map_benefit_type(apolice_props.get("apolice___beneficio"))
    policy.benefit_type = BenefitType(benefit_raw) if benefit_raw else None
    policy.mrr_projected = parse_decimal(ticket_props.get("mrr___receita_mensal"))

    # Lockable — only update if not locked
    if not locked:
        if ev:
            policy.ev_id = ev.id
        if client_obj:
            policy.client_id = client_obj.id
        segment_raw = map_segment(ticket_props.get("cotar___segmentacao_pipo"))
        policy.segment = Segment(segment_raw) if segment_raw else None
        policy.closed_date = parse_date(ticket_props.get("closed_date"))

    db.session.flush()
    return is_new


def _filter_tickets_with_default_deal(client, ticket_ids, summary):
    """Phase 4 — verify each ticket has at least one associated deal in the
    default pipeline. Returns set of ticket_ids that pass.
    """
    ticket_ids = list(ticket_ids)
    if not ticket_ids:
        return set()
    ticket_to_deals = client.batch_read_associations("tickets", "deals", ticket_ids)
    all_deal_ids = list({d for deals in ticket_to_deals.values() for d in deals})
    deal_props = client.batch_read_objects(
        "deals", all_deal_ids, DEAL_VALIDATION_PROPERTIES
    )
    valid = set()
    for ticket_id in ticket_ids:
        deals_for_ticket = ticket_to_deals.get(ticket_id, [])
        has_default = any(
            deal_props.get(d, {}).get("hs_pipeline") == DEFAULT_DEAL_PIPELINE_ID
            for d in deals_for_ticket
        )
        if has_default:
            valid.add(ticket_id)
        else:
            summary["skipped"]["no_default_deal"] += 1
    logger.info(f"_filter_tickets_with_default_deal: {len(valid)}/{len(ticket_ids)} tickets pass")
    return valid
