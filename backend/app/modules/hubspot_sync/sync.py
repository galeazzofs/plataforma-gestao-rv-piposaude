"""HubSpot sync — apolice-anchored.

Orchestrates pulling apolices (deals in pipeline 2453678), validating their
ticket+default-deal linkage, and upserting one row in `policies` per apolice.

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

VALID_BENEFITS_HUBSPOT = ["Saúde", "Odonto", "Vida", "Saúde e Odonto"]

APOLICE_PROPERTIES = ["apolice___beneficio", "numero_apolice", "parceiro"]
TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "cliente___nome_da_empresa",
    "hs_pipeline", "hs_pipeline_stage",
]
DEAL_VALIDATION_PROPERTIES = ["hs_pipeline"]


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


def _upsert_policy(apolice, ticket_props, owner_map, ticket_id=None,
                   ev_lookup=None, ev_name_lookup=None, ev_override_lookup=None):
    """Phase 5 — create or update one Policy row from an apolice + its ticket.

    Args:
        apolice: dict from HubSpot search (has `id` and `properties`)
        ticket_props: dict of ticket properties (already validated/filtered)
        owner_map: dict {owner_id_str: {"email": ..., "name": ...}}
        ticket_id: HubSpot ticket id; pulled from caller's apolice→ticket map
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
        "skipped": {
            "no_ticket": 0,
            "wrong_pipeline": 0,
            "not_gongo": 0,
            "too_old": 0,
            "no_default_deal": 0,
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
    # Total skipped across all reasons (legacy single-int field consumed by UI)
    skipped_total = sum(summary["skipped"].values()) if isinstance(summary["skipped"], dict) else summary["skipped"]
    PlatformSetting.set("hubspot_last_sync_skipped", skipped_total, user_id=None)
    db.session.commit()


def run_sync():
    """Main sync job: pull apolices from HubSpot, validate linkage, upsert into policies.

    Only processes apolices whose linked ticket's solicitante_demanda resolves
    to an active EV/CN user in the platform (cascade: email local → normalized
    name → manual hubspot_owner_map override).

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
        apolices = _fetch_apolices(client)
        apolice_to_ticket = _fetch_apolice_tickets(client, apolices, summary)
        tickets = _fetch_and_validate_tickets(
            client, apolice_to_ticket.values(), summary
        )
        valid_ticket_ids = _filter_tickets_with_default_deal(
            client, tickets.keys(), summary
        )
    except Exception as e:
        logger.error(f"HubSpot fetch failed: {e}")
        summary["errors"].append(f"Fetch failed: {e}")
        summary["error_count"] = len(summary["errors"])
        summary["timestamp"] = datetime.now(timezone.utc).isoformat()
        _persist_last_sync(summary)
        return summary

    for apolice in apolices:
        apolice_id = apolice["id"]
        ticket_id = apolice_to_ticket.get(apolice_id)
        if not ticket_id or ticket_id not in valid_ticket_ids:
            continue
        try:
            result = _upsert_policy(
                apolice, tickets[ticket_id], owner_map, ticket_id=ticket_id,
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
