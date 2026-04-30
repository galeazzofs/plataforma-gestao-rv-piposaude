"""HubSpot sync — apolice-anchored.

Orchestrates pulling apolices (deals in pipeline 2453678), validating their
ticket+default-deal linkage, and upserting one row in `policies` per apolice.

See docs/superpowers/specs/2026-04-29-policy-sync-from-apolices-pipeline-design.md
"""
import logging
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import User, Policy, Client
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
