"""CN realized values sync — pulls SAO count + vidas sum per CN per month
from HubSpot deals in the default (oportunidades) pipeline.

A deal counts toward a CN's apuração for (month, year) when:
- pipeline = "default"
- hs_v2_date_entered_9102669 falls within [month_start, next_month_start)
- the deal's `cn` property matches an active User.name (role=CN) after
  normalization (lowercase, accent-stripped).

Aggregation:
- sao_realizado    = count of matching deals
- vidas_realizado  = sum of numero_de_vidas_previstas (missing → 0)

Pure read of HubSpot — no DB writes. Caller (the API layer) converts the
returned dict into the `inputs` list consumed by
`run_cn_monthly_appraisal_with_inputs`.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
import logging

from app.models import User, UserRole
from app.modules.hubspot_sync.client import HubSpotClient
from app.modules.hubspot_sync.mapper import parse_decimal
from app.modules.hubspot_sync.sync import (
    DEFAULT_DEAL_PIPELINE_ID, _normalize_owner_name,
)

logger = logging.getLogger(__name__)

SAO_STAGE_DATE_PROPERTY = "hs_v2_date_entered_9102669"
VIDAS_PROPERTY = "numero_de_vidas_previstas"
CN_NAME_PROPERTY = "cn"
DEAL_SEARCH_PROPERTIES = [
    "pipeline",
    CN_NAME_PROPERTY,
    SAO_STAGE_DATE_PROPERTY,
    VIDAS_PROPERTY,
]


def _month_bounds(month: int, year: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _to_ms(d: date) -> int:
    # hs_v2_date_entered_* is a datetime property; HubSpot search expects
    # millisecond epoch values for datetime filters.
    return int(
        datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000
    )


def _fetch_deals_entered_sao_in(client, month: int, year: int) -> list[dict]:
    start, end = _month_bounds(month, year)
    filters = [
        {"propertyName": "pipeline", "operator": "EQ",
         "value": DEFAULT_DEAL_PIPELINE_ID},
        {"propertyName": SAO_STAGE_DATE_PROPERTY, "operator": "GTE",
         "value": str(_to_ms(start))},
        {"propertyName": SAO_STAGE_DATE_PROPERTY, "operator": "LT",
         "value": str(_to_ms(end))},
    ]
    deals = []
    after = None
    while True:
        result = client.search_deals(
            filters=filters, properties=DEAL_SEARCH_PROPERTIES, after=after,
        )
        deals.extend(result.get("results", []))
        next_cursor = result.get("paging", {}).get("next", {}).get("after")
        if not next_cursor:
            break
        after = next_cursor
    return deals


def fetch_cn_realized_with_meta(month: int, year: int, client=None):
    """Return (by_cn, meta). `by_cn` is the dict consumed by the calculator;
    `meta` exposes `deals_scanned` and `unresolved` (deals whose `cn`
    property didn't match any active CN) so the admin UI can distinguish
    "HubSpot returned 0 deals" from "deals exist but no CN matched".
    """
    client = client or HubSpotClient()

    deals = _fetch_deals_entered_sao_in(client, month, year)
    if not deals:
        logger.info(
            f"fetch_cn_realized({month}/{year}): 0 deals entered SAO this month"
        )
        return {}, {"deals_scanned": 0, "unresolved": 0}

    active_cns = User.query.filter_by(role=UserRole.CN, active=True).all()
    cn_by_norm_name = {_normalize_owner_name(u.name): u for u in active_cns}

    out = {}
    unresolved = 0
    for d in deals:
        props = d.get("properties", {}) or {}
        raw_cn_name = props.get(CN_NAME_PROPERTY)
        cn = (cn_by_norm_name.get(_normalize_owner_name(raw_cn_name))
              if raw_cn_name else None)
        if cn is None:
            unresolved += 1
            continue

        vidas = parse_decimal(props.get(VIDAS_PROPERTY)) or Decimal("0")
        bucket = out.setdefault(
            cn.id, {"sao_realizado": Decimal("0"),
                    "vidas_realizado": Decimal("0")},
        )
        bucket["sao_realizado"] += Decimal("1")
        bucket["vidas_realizado"] += vidas

    logger.info(
        f"fetch_cn_realized({month}/{year}): {len(out)} CNs hit "
        f"({len(deals)} deals scanned, {unresolved} unresolved)"
    )
    return out, {"deals_scanned": len(deals), "unresolved": unresolved}


def fetch_cn_realized(month: int, year: int, client=None) -> dict:
    """Backwards-compatible wrapper — returns just the by-CN dict."""
    by_cn, _ = fetch_cn_realized_with_meta(month, year, client=client)
    return by_cn
