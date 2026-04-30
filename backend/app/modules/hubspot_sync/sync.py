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
