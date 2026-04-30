"""HubSpot sync — ticket-anchored, full-fetch.

Starts from tickets in the placement pipeline at the gongo stage, fetches
their associated apolice deals, and upserts one row in `policies` per
apolice. A single ticket can drive multiple apolices (e.g. saude + odonto
for the same client) — all are captured.

Filter at the source: the most restrictive criteria (pipeline + stage +
closed_date) live on tickets, so we search there first instead of
pulling 9k+ apolices and filtering after.

Full-fetch every run: apólice deal stage changes (e.g. moving into
Pré-ativação) don't bump the ticket's hs_lastmodifieddate, so an
incremental cursor on tickets would silently miss them. Delete-by-absence
(handled in a later phase) keeps the row count bounded against drift.

Only syncs apolices whose linked ticket's solicitante_demanda matches an
active EV/CN user in the platform. Matching cascade: email local part →
normalized owner name (strips deactivation suffix) → manual override via
PlatformSetting "hubspot_owner_map".

See docs/superpowers/specs/2026-04-29-policy-sync-from-apolices-pipeline-design.md
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
DEFAULT_DEAL_PIPELINE_ID = "default"
GONGO_DATE_FLOOR = date(2024, 9, 1)

PRE_ATIVACAO_STAGE_ID = "14038792"
PRE_ATIVACAO_DATE_FLOOR = date(2024, 9, 1)

VALID_BENEFITS_HUBSPOT = ["Saúde", "Odonto", "Vida", "Saúde e Odonto"]

TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "cliente___nome_da_empresa",
    "hs_pipeline", "hs_pipeline_stage",
]
# Single batch_read pulls both classification (`pipeline`) and the apolice-
# specific properties — saves a round trip per ticket batch.
DEAL_PROPERTIES = [
    "pipeline",
    "apolice___beneficio", "numero_apolice", "parceiro",
    "hs_v2_date_entered_14038792",
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
    """Extract email and name from owner_map entry, with fallback.

    owner_map values are {email, name} dicts from get_all_owners().
    Tolerates legacy string values ({owner_id: email}) for back-compat.
    If the key isn't found, treat owner_id_or_email as an email directly.
    """
    info = owner_map.get(str(owner_id_or_email)) if owner_id_or_email else None
    if isinstance(info, dict):
        return info.get("email"), info.get("name") or ""
    if isinstance(info, str):
        return info, ""
    # Fallback: the field may already contain an email
    return owner_id_or_email, ""


def _resolve_ev(ticket_props, owner_map, ev_lookup, ev_name_lookup, ev_override_lookup):
    """Resolve solicitante_demanda → User via owner_map + 3-step cascade.

    Returns the User instance or None if no active EV matches.
    """
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

    Filters applied at source:
    - hs_pipeline = PLACEMENT_PIPELINE_ID    (placement / sales pipeline)
    - hs_pipeline_stage = GONGO_STAGE_ID     (gongo stage = closed-won)
    - closed_date >= GONGO_DATE_FLOOR        (project-defined recent floor)

    Full-fetch every run — apólice deal stage changes don't update the ticket's
    hs_lastmodifieddate, so an incremental cursor on tickets would miss them.

    Returns the raw list of ticket dicts (each with `id` and `properties`).
    """
    filters = [
        {"propertyName": "hs_pipeline", "operator": "EQ", "value": PLACEMENT_PIPELINE_ID},
        {"propertyName": "hs_pipeline_stage", "operator": "EQ", "value": GONGO_STAGE_ID},
        {"propertyName": "closed_date", "operator": "GTE", "value": GONGO_DATE_FLOOR.isoformat()},
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


def _resolve_ticket_apolices(client, tickets, summary):
    """Phase 2 — for each ticket, identify the associated apolice deal(s)
    and verify a default-pipeline deal exists.

    A single ticket can drive multiple apolices (saúde + odonto, etc.) —
    all are captured. Tickets without a default deal or without any
    valid-benefit apolice are dropped (counted in summary).

    Returns dict {ticket_id: [apolice_dict, ...]} where each apolice_dict
    has `id` and `properties` (already populated with apolice___beneficio,
    numero_apolice, parceiro from the same batch_read).
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
        apolices = []
        has_default = False
        for d in deals_for_ticket:
            props = deal_props.get(d, {})
            pipeline = props.get("pipeline")
            if pipeline == APOLICE_PIPELINE_ID:
                if props.get("apolice___beneficio") not in VALID_BENEFITS_HUBSPOT:
                    continue
                entered = parse_date(props.get("hs_v2_date_entered_14038792"))
                if entered is None or entered < PRE_ATIVACAO_DATE_FLOOR:
                    summary["skipped"]["not_pre_activation"] += 1
                    continue
                apolices.append({"id": d, "properties": props})
            elif pipeline == DEFAULT_DEAL_PIPELINE_ID:
                has_default = True
        if not has_default:
            summary["skipped"]["no_default_deal"] += 1
            continue
        if not apolices:
            summary["skipped"]["no_apolice"] += 1
            continue
        out[ticket_id] = apolices
    logger.info(
        f"_resolve_ticket_apolices: {len(out)}/{len(ticket_ids)} tickets "
        f"have valid apolice + default deal"
    )
    return out


def _upsert_policy(apolice, ticket_props, owner_map, ticket_id=None,
                   ev_lookup=None, ev_name_lookup=None, ev_override_lookup=None):
    """Phase 3 — create or update one Policy row from an apolice + its ticket.

    Args:
        apolice: dict from HubSpot (has `id` and `properties`)
        ticket_props: dict of ticket properties (already validated/filtered)
        owner_map: dict {owner_id_str: {"email": ..., "name": ...}}
        ticket_id: HubSpot ticket id; pulled from caller's ticket→apolice map
        ev_lookup: dict {email_local: User} of active EVs (optional, for backward-compat)
        ev_name_lookup: dict {normalized_name: User} (optional)
        ev_override_lookup: dict {hubspot_owner_id: User} (optional, for deleted users)

    Returns True if a new row was created, False if updated. Returns None
    if the apolice was skipped because no active EV matched (caller increments
    summary["skipped"]["no_active_ev"]).

    Respects Policy.is_locked: locked rows keep ev_id, client_id, segment, closed_date.
    """
    ev_lookup = ev_lookup or {}
    ev_name_lookup = ev_name_lookup or {}
    ev_override_lookup = ev_override_lookup or {}
    apolice_id = apolice["id"]
    apolice_props = apolice.get("properties", {})

    # Resolve EV via the same cascade master uses (email local → name → override).
    # When no lookups are provided (legacy/test path), fall back to the simple
    # owner_map → email lookup so isolated _upsert_policy tests still work.
    if ev_lookup or ev_name_lookup or ev_override_lookup:
        ev = _resolve_ev(ticket_props, owner_map, ev_lookup, ev_name_lookup, ev_override_lookup)
        if ev is None:
            return None  # caller decides how to count this skip
    else:
        raw_ev = ticket_props.get("solicitante_demanda")
        ev_email, _ = _resolve_owner_info(owner_map, raw_ev) if raw_ev else (None, "")
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
        policy.closed_date = parse_date(ticket_props.get("closed_date"))

    db.session.flush()
    return is_new


# --- Orchestrator ---

def _new_summary():
    return {
        "timestamp": None,
        "created": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": {
            "no_default_deal": 0,
            "no_apolice": 0,
            "no_active_ev": 0,
            "not_pre_activation": 0,
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
    apolice + default deals, and upsert into `policies`.

    Every run is a full fetch from `GONGO_DATE_FLOOR` forward — apólice deal
    stage changes don't update ticket hs_lastmodifieddate, so an incremental
    cursor would miss them.

    Returns summary dict.
    """
    client = HubSpotClient()
    summary = _new_summary()

    # Pre-load active EV/CN users from platform DB
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

    # Manual owner ID overrides for users fully deleted from HubSpot
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

    # Owner map (HubSpot owner_id → {email, name})
    try:
        owner_map = client.get_all_owners()
        logger.info(f"Loaded {len(owner_map)} HubSpot owners")
    except Exception as e:
        logger.warning(f"Could not load owners: {e}")
        owner_map = {}

    try:
        tickets = _fetch_tickets(client)
        ticket_to_apolices = _resolve_ticket_apolices(client, tickets, summary)
    except Exception as e:
        logger.error(f"HubSpot fetch failed: {e}")
        summary["errors"].append(f"Fetch failed: {e}")
        summary["error_count"] = len(summary["errors"])
        summary["timestamp"] = datetime.now(timezone.utc).isoformat()
        _persist_last_sync(summary)
        return summary

    ticket_props_by_id = {t["id"]: t.get("properties", {}) for t in tickets}

    for ticket_id, apolices in ticket_to_apolices.items():
        ticket_props = ticket_props_by_id.get(ticket_id, {})
        for apolice in apolices:
            apolice_id = apolice["id"]
            try:
                result = _upsert_policy(
                    apolice, ticket_props, owner_map, ticket_id=ticket_id,
                    ev_lookup=ev_lookup,
                    ev_name_lookup=ev_name_lookup,
                    ev_override_lookup=ev_override_lookup,
                )
                if result is None:
                    summary["skipped"]["no_active_ev"] += 1
                elif result:
                    summary["created"] += 1
                else:
                    summary["updated"] += 1
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error processing apolice {apolice_id}: {e}")
                summary["errors"].append(f"Apolice {apolice_id}: {e}")

    db.session.commit()
    summary["error_count"] = len(summary["errors"])
    summary["timestamp"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"HubSpot sync completed: {summary}")
    _persist_last_sync(summary)
    return summary
