"""HubSpot sync — ticket-anchored, full-fetch, 1 Policy per ticket.

Searches tickets in the Placement pipeline, Gongo stage, with team
solicitante = "Vendas" and closed_date >= 2024-09-01. For each ticket,
identifies the apólice deal (must have entered pré-ativação) and the
default-pipeline deal. Upserts one row in `policies` per ticket.

Source-of-truth per field:
- ticket             → ev_id, client_id, segment, mrr_projected
- apólice deal       → numero_apolice, partner_operator, benefit_type
- default deal       → closed_date  (from `closedate`)

Premise: each ticket has exactly one apólice in pré-ativação. If more,
the first is used and a warning is logged. If none, the ticket is skipped
until an apólice advances.

Sync is full-fetch every run + delete-by-absence — `policies` mirrors
HubSpot 1:1 by ticket id. Tickets missing from a clean fetch are deleted
(commissions/ev_validations cascaded; financial_imports unlinked).

EV resolution cascade (unchanged): owner_map → email local part →
normalized owner name → manual override via PlatformSetting
"hubspot_owner_map".

See docs/superpowers/specs/2026-04-30-ticket-anchored-sync-redesign-design.md
"""
import logging
import re
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import User, Policy, Client, BenefitType, Segment, PlatformSetting
from app.modules.hubspot_sync.client import HubSpotClient
from app.modules.hubspot_sync.mapper import (
    map_segment, map_benefit_type, parse_date, parse_decimal,
)

logger = logging.getLogger(__name__)

# --- HubSpot pipeline / stage IDs ---
APOLICE_PIPELINE_ID = "2453678"
PLACEMENT_PIPELINE_ID = "651307"
GONGO_STAGE_ID = "11947921"
PRE_ATIVACAO_STAGE_ID = "14038792"
DEFAULT_DEAL_PIPELINE_ID = "default"
GONGO_DATE_FLOOR = date(2024, 9, 1)
PRE_ATIVACAO_DATE_FLOOR = date(2024, 9, 1)

VALID_BENEFITS_HUBSPOT = ["Saúde", "Odonto", "Vida", "Saúde e Odonto"]
TIME_SOLICITANTE_VENDAS = "Vendas"

TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "cliente___nome_da_empresa",
    "hs_pipeline", "hs_pipeline_stage",
    "time_solicitante",
]
# Single batch_read pulls pipeline classification + apolice props + default
# deal closedate — saves a round trip per ticket batch.
DEAL_PROPERTIES = [
    "pipeline",
    "apolice___beneficio", "numero_apolice", "parceiro",
    "hs_v2_date_entered_14038792",
    "closedate",
]


# --- EV / owner resolution helpers ---

def _email_local(email):
    """Return the local part of an email (before @)."""
    return email.split("@")[0].lower() if email else ""


def _strip_accents(s):
    """NFD-decompose and drop combining marks."""
    import unicodedata
    if not s:
        return ""
    decomp = unicodedata.normalize("NFD", str(s).strip().lower())
    return "".join(c for c in decomp if unicodedata.category(c) != "Mn")


def _normalize_owner_name(name):
    """Normalize a HubSpot owner name for matching.

    HubSpot appends suffixes like "(usuario desativado/removido)" to deactivated
    user names. Strip any trailing parenthetical before comparing to platform names.
    """
    if not name:
        return ""
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    return _strip_accents(stripped)


def _build_ev_lookup(active_evs):
    """Build a lookup from email local part → User for active EVs.

    Handles domain mismatch (e.g. @piposaude.com in HubSpot vs
    @piposaude.com.br in the platform).
    """
    return {_email_local(u.email): u for u in active_evs}


def _build_ev_name_lookup(active_evs):
    """Build a lookup from normalized full name → User for active EVs.

    Used as fallback when email local-part matching fails.
    """
    return {_strip_accents(u.name): u for u in active_evs}


def _resolve_owner_info(owner_map, owner_id_or_email):
    """Extract email and name from owner_map entry, with fallback."""
    info = owner_map.get(str(owner_id_or_email)) if owner_id_or_email else None
    if isinstance(info, dict):
        return info.get("email"), info.get("name") or ""
    if isinstance(info, str):
        return info, ""
    return owner_id_or_email, ""


def _resolve_ev(ticket_props, owner_map, ev_lookup, ev_name_lookup, ev_override_lookup):
    """Resolve solicitante_demanda → User via owner_map + 3-step cascade."""
    raw = ticket_props.get("solicitante_demanda")
    if not raw:
        return None
    ev_email, ev_owner_name = _resolve_owner_info(owner_map, raw)
    ev = ev_lookup.get(_email_local(ev_email)) if ev_email else None
    if ev is None and ev_owner_name:
        ev = ev_name_lookup.get(_normalize_owner_name(ev_owner_name))
    if ev is None:
        ev = ev_override_lookup.get(str(raw))
    return ev


# --- Sync phases ---

def _fetch_tickets(client):
    """Phase 1 — search tickets matching all gating criteria upfront.

    Filters at source:
    - hs_pipeline = PLACEMENT_PIPELINE_ID
    - hs_pipeline_stage = GONGO_STAGE_ID
    - closed_date >= GONGO_DATE_FLOOR
    - time_solicitante = "Vendas"

    Full-fetch every run — apólice stage transitions don't bump the ticket's
    hs_lastmodifieddate, so an incremental cursor would silently miss them.
    """
    filters = [
        {"propertyName": "hs_pipeline", "operator": "EQ", "value": PLACEMENT_PIPELINE_ID},
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": GONGO_STAGE_ID},
        {"propertyName": "closed_date", "operator": "GTE", "value": GONGO_DATE_FLOOR.isoformat()},
        {"propertyName": "time_solicitante", "operator": "EQ", "value": TIME_SOLICITANTE_VENDAS},
    ]

    tickets = []
    after = None
    while True:
        result = client.search_tickets(
            filters=filters, properties=TICKET_PROPERTIES, after=after,
        )
        tickets.extend(result.get("results", []))
        next_cursor = result.get("paging", {}).get("next", {}).get("after")
        if not next_cursor:
            break
        after = next_cursor
    logger.info(f"_fetch_tickets: {len(tickets)} tickets matched (full fetch)")
    return tickets


def _resolve_ticket_deals(client, tickets, summary):
    """Phase 2 — for each ticket, identify (apólice, default_deal) pair.

    Selection rules:
    - apólice deal: pipeline=APOLICE_PIPELINE_ID, valid benefit, entered
      pré-ativação >= 2024-09-01. If multiple match, first one is used and
      summary["skipped"]["multiple_apolices"] is bumped (warning, not skip).
    - default deal: pipeline=DEFAULT_DEAL_PIPELINE_ID. First match used.

    Tickets without a valid apólice OR without a default deal are skipped.
    Returns dict {ticket_id: {"apolice": dict, "default_deal": dict}}.
    """
    if not tickets:
        return {}
    ticket_ids = [t["id"] for t in tickets]
    ticket_to_deals = client.batch_read_associations("tickets", "deals", ticket_ids)
    all_deal_ids = list({d for deals in ticket_to_deals.values() for d in deals})
    deal_props = client.batch_read_objects("deals", all_deal_ids, DEAL_PROPERTIES)

    out = {}
    for ticket_id in ticket_ids:
        deals_for_ticket = ticket_to_deals.get(ticket_id, [])
        apolices_in_pre_ativacao = []
        default_deal = None
        for d in deals_for_ticket:
            props = deal_props.get(d, {})
            pipeline = props.get("pipeline")
            if pipeline == APOLICE_PIPELINE_ID:
                if props.get("apolice___beneficio") not in VALID_BENEFITS_HUBSPOT:
                    continue
                entered = parse_date(props.get("hs_v2_date_entered_14038792"))
                if entered is None or entered < PRE_ATIVACAO_DATE_FLOOR:
                    continue
                apolices_in_pre_ativacao.append({"id": d, "properties": props})
            elif pipeline == DEFAULT_DEAL_PIPELINE_ID:
                if default_deal is None:
                    default_deal = {"id": d, "properties": props}
        if not apolices_in_pre_ativacao:
            summary["skipped"]["no_apolice_pre_ativacao"] += 1
            continue
        if default_deal is None:
            summary["skipped"]["no_default_deal"] += 1
            continue
        if len(apolices_in_pre_ativacao) > 1:
            summary["skipped"]["multiple_apolices"] += 1
            logger.warning(
                f"Ticket {ticket_id} has {len(apolices_in_pre_ativacao)} apólices "
                f"in pré-ativação; using first ({apolices_in_pre_ativacao[0]['id']})"
            )
        out[ticket_id] = {
            "apolice": apolices_in_pre_ativacao[0],
            "default_deal": default_deal,
        }
    logger.info(
        f"_resolve_ticket_deals: {len(out)}/{len(ticket_ids)} tickets resolved "
        f"(have apólice in pré-ativação + default deal)"
    )
    return out


def _upsert_policy(ticket_id, ticket_props, apolice, default_deal, owner_map,
                   ev_lookup=None, ev_name_lookup=None, ev_override_lookup=None):
    """Phase 3 — create or update one Policy row from a ticket + its deals.

    Returns True on create, False on update, None when skipped (no active EV).
    Respects Policy.is_locked: locked rows preserve ev_id, client_id, segment, closed_date.
    """
    ev_lookup = ev_lookup or {}
    ev_name_lookup = ev_name_lookup or {}
    ev_override_lookup = ev_override_lookup or {}
    apolice_props = apolice.get("properties", {})
    default_deal_props = default_deal.get("properties", {})

    if ev_lookup or ev_name_lookup or ev_override_lookup:
        ev = _resolve_ev(ticket_props, owner_map, ev_lookup, ev_name_lookup, ev_override_lookup)
        if ev is None:
            return None
    else:
        # Legacy fallback for isolated test calls without lookups.
        raw_ev = ticket_props.get("solicitante_demanda")
        ev_email, _ = _resolve_owner_info(owner_map, raw_ev) if raw_ev else (None, "")
        ev = User.query.filter_by(email=ev_email).first() if ev_email else None

    client_name = ticket_props.get("cliente___nome_da_empresa") or ""
    client_obj = None
    if client_name:
        client_obj = Client.find_or_create(client_name, ev_id=ev.id if ev else None)
        db.session.flush()

    policy = Policy.query.filter_by(hubspot_ticket_id=str(ticket_id)).first()
    is_new = policy is None
    if is_new:
        policy = Policy(hubspot_ticket_id=str(ticket_id))
        db.session.add(policy)

    locked = bool(getattr(policy, "is_locked", False))

    # Always update (non-lockable):
    policy.hubspot_apolice_id = str(apolice["id"])
    policy.numero_apolice = apolice_props.get("numero_apolice") or None
    parceiro = apolice_props.get("parceiro")
    policy.partner_operator = parceiro.strip() if parceiro else None
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
        policy.closed_date = parse_date(default_deal_props.get("closedate"))

    db.session.flush()
    return is_new


def _delete_absent_policies(seen_ticket_ids, summary):
    """Phase 4 — delete policies whose hubspot_ticket_id wasn't in this fetch.

    Cascade:
    - DELETE FROM commissions WHERE policy_id IN (...)
    - DELETE FROM ev_validations WHERE policy_id IN (...)
    - UPDATE financial_imports SET policy_id = NULL WHERE policy_id IN (...)
    - DELETE FROM policies WHERE id IN (...)

    Includes locked rows — lock prevents overwrite during upsert, not deletion
    when the source disappears.

    Safety guard: if seen_ticket_ids is empty AND policies has rows, abort with
    an error in summary["errors"]. A zero-result fetch against a populated DB
    is more likely a HubSpot anomaly (silent pipeline change, expired token
    returning 200) than a real wipe.
    """
    from app.models import Commission, EvValidation, FinancialImport

    if not seen_ticket_ids and Policy.query.count() > 0:
        msg = "Delete-by-absence abortado: fetch retornou zero tickets mas DB não está vazio"
        logger.error(msg)
        summary["errors"].append(msg)
        summary["error_count"] = len(summary["errors"])
        return

    absent = Policy.query.filter(
        Policy.hubspot_ticket_id.notin_(list(seen_ticket_ids))
    ).all()

    if not absent:
        return

    absent_ids = [p.id for p in absent]

    Commission.query.filter(Commission.policy_id.in_(absent_ids)).delete(synchronize_session=False)
    EvValidation.query.filter(EvValidation.policy_id.in_(absent_ids)).delete(synchronize_session=False)
    FinancialImport.query.filter(FinancialImport.policy_id.in_(absent_ids)).update(
        {FinancialImport.policy_id: None}, synchronize_session=False
    )
    Policy.query.filter(Policy.id.in_(absent_ids)).delete(synchronize_session=False)

    summary["deleted"] = len(absent_ids)
    logger.info(
        f"Delete-by-absence: {len(absent_ids)} policies removidas "
        f"(commissions/ev_validations cascateadas, financial_imports unlinked)"
    )


# --- Orchestrator ---

def _new_summary():
    return {
        "timestamp": None,
        "created": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": {
            "no_apolice_pre_ativacao": 0,
            "no_default_deal": 0,
            "multiple_apolices": 0,
            "no_active_ev": 0,
        },
        "errors": [],
        "error_count": 0,
    }


def _persist_last_sync(summary):
    """Mirror sync summary into PlatformSetting so the admin UI can show it."""
    PlatformSetting.set("hubspot_last_sync", summary["timestamp"], user_id=None)
    PlatformSetting.set("hubspot_last_sync_errors", summary["errors"], user_id=None)
    PlatformSetting.set("hubspot_last_sync_created", summary["created"], user_id=None)
    PlatformSetting.set("hubspot_last_sync_updated", summary["updated"], user_id=None)
    PlatformSetting.set("hubspot_last_sync_deleted", summary["deleted"], user_id=None)
    skipped_total = sum(summary["skipped"].values()) if isinstance(summary["skipped"], dict) else summary["skipped"]
    PlatformSetting.set("hubspot_last_sync_skipped", skipped_total, user_id=None)
    db.session.commit()


def run_sync():
    """Main sync job: pull tickets matching gating criteria, resolve their
    apólice + default deals, and upsert into `policies`. Then delete any
    policies whose ticket id is no longer in the HubSpot result set.

    Returns summary dict.
    """
    client = HubSpotClient()
    summary = _new_summary()

    from app.models import UserRole
    active_evs = User.query.filter(
        User.role.in_([UserRole.EV, UserRole.CN]),
        User.active.is_(True),
    ).all()
    ev_lookup = _build_ev_lookup(active_evs)
    ev_name_lookup = _build_ev_name_lookup(active_evs)
    logger.info(f"Active EVs in platform: {len(ev_lookup)}")

    if not ev_lookup:
        logger.warning("No active EVs found — nothing to sync")
        summary["timestamp"] = datetime.now(timezone.utc).isoformat()
        summary["errors"].append("No active EVs in platform")
        summary["error_count"] = 1
        _persist_last_sync(summary)
        return summary

    raw_owner_map_setting = PlatformSetting.get("hubspot_owner_map") or {}
    ev_override_lookup = {}
    for oid, email in raw_owner_map_setting.items():
        local = _email_local(email)
        u = ev_lookup.get(local)
        if u:
            ev_override_lookup[str(oid)] = u
        else:
            logger.warning(f"hubspot_owner_map: {oid}→{email!r} doesn't match any active EV")
    if ev_override_lookup:
        logger.info(f"Manual owner overrides loaded: {list(ev_override_lookup.keys())}")

    try:
        owner_map = client.get_all_owners()
        logger.info(f"Loaded {len(owner_map)} HubSpot owners")
    except Exception as e:
        logger.warning(f"Could not load owners: {e}")
        owner_map = {}

    try:
        tickets = _fetch_tickets(client)
        ticket_to_deals = _resolve_ticket_deals(client, tickets, summary)
    except Exception as e:
        logger.error(f"HubSpot fetch failed: {e}")
        summary["errors"].append(f"Fetch failed: {e}")
        summary["error_count"] = len(summary["errors"])
        summary["timestamp"] = datetime.now(timezone.utc).isoformat()
        _persist_last_sync(summary)
        return summary

    ticket_props_by_id = {t["id"]: t.get("properties", {}) for t in tickets}

    unmatched_owners = {}
    for ticket_id, deals in ticket_to_deals.items():
        ticket_props = ticket_props_by_id.get(ticket_id, {})
        try:
            result = _upsert_policy(
                ticket_id, ticket_props,
                deals["apolice"], deals["default_deal"],
                owner_map,
                ev_lookup=ev_lookup,
                ev_name_lookup=ev_name_lookup,
                ev_override_lookup=ev_override_lookup,
            )
            if result is None:
                summary["skipped"]["no_active_ev"] += 1
                raw_owner = ticket_props.get("solicitante_demanda") or "<empty>"
                unmatched_owners[str(raw_owner)] = unmatched_owners.get(str(raw_owner), 0) + 1
            elif result:
                summary["created"] += 1
            else:
                summary["updated"] += 1
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing ticket {ticket_id}: {e}")
            summary["errors"].append(f"Ticket {ticket_id}: {e}")

    if unmatched_owners:
        # Surface raw solicitante_demanda values so admins can map them in
        # PlatformSetting "hubspot_owner_map". Sorted by frequency descending.
        ranked = sorted(unmatched_owners.items(), key=lambda kv: -kv[1])
        logger.warning(
            "Skipped %d ticket(s) with no matching active EV. "
            "Top unmatched solicitante_demanda values: %s",
            sum(unmatched_owners.values()),
            ", ".join(f"{raw}({count})" for raw, count in ranked[:10]),
        )

    db.session.commit()
    summary["error_count"] = len(summary["errors"])

    if summary["error_count"] == 0:
        seen_ticket_ids = set(ticket_to_deals.keys())
        _delete_absent_policies(seen_ticket_ids, summary)
        db.session.commit()
        # Re-evaluate: _delete_absent_policies may have appended a guard error.
        summary["error_count"] = len(summary["errors"])

    summary["timestamp"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"HubSpot sync completed: {summary}")
    _persist_last_sync(summary)
    return summary
