"""HubSpot sync — ticket-anchored, full-fetch, 1 Policy per ticket.

Searches tickets in the Placement pipeline, Gongo stage, with
closed_date >= 2024-09-01. For each ticket, requires an associated deal
in the default pipeline (oportunidades) AND an apólice deal that has
entered pré-ativação. Upserts one row in `policies` per ticket.

Source-of-truth per field:
- ticket             → ev_id, client_id, segment, mrr_projected, benefit_type
- apólice deal       → numero_apolice, partner_operator
- default deal       → closed_date (from `closedate`); presence is required

Premise: each ticket has exactly one apólice in pré-ativação. If more,
the first is used and a warning is logged. If none, the ticket is skipped
until an apólice advances.

Sync is full-fetch every run + delete-by-absence — `policies` mirrors
HubSpot 1:1 by ticket id. Tickets missing from a clean fetch are deleted
(commissions/ev_validations cascaded; financial_imports unlinked).

EV resolution: matches the platform's full EV/CN user list (active +
inactive — historical apólices owned by deactivated EVs must still
sync). Cascade: owner_map → email local part → normalized owner name →
manual override via PlatformSetting "hubspot_owner_map".

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
ATIVACAO_STAGE_ID = "8438571"
APOLICE_ATIVA_STAGE_ID = "8438574"
APOLICE_INATIVA_STAGE_ID = "9015565"
APOLICE_VALID_STAGES = {
    PRE_ATIVACAO_STAGE_ID, ATIVACAO_STAGE_ID,
    APOLICE_ATIVA_STAGE_ID, APOLICE_INATIVA_STAGE_ID,
}
DEFAULT_DEAL_PIPELINE_ID = "default"
# Default-pipeline deal must be at one of these stages to count as the
# ticket's "closing deal" — replaces team-level filtering (time_solicitante
# isn't reliably populated). Other-team tickets land at earlier stages and
# are filtered out by this gate.
PROPOSTA_ACEITA_STAGE_ID = "26183057"
GANHO_STAGE_ID = "closedwon"
DEFAULT_DEAL_VALID_STAGES = {PROPOSTA_ACEITA_STAGE_ID, GANHO_STAGE_ID}
GONGO_DATE_FLOOR = date(2024, 9, 1)
PRE_ATIVACAO_DATE_FLOOR = date(2024, 9, 1)

VALID_BENEFITS_HUBSPOT = ["Saúde", "Odonto", "Vida", "Saúde e Odonto"]

TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "cliente___nome_da_empresa",
    "beneficio_a_ser_cotado",
    "hs_pipeline", "hs_pipeline_stage",
]
# Single batch_read pulls pipeline classification + apolice props + default
# deal closedate — saves a round trip per ticket batch.
DEAL_PROPERTIES = [
    "pipeline", "dealstage",
    "numero_apolice", "parceiro",
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

    Team-level filtering (e.g. solicitante = Vendas) can't be applied here
    because time_solicitante isn't reliably populated. Non-Vendas tickets
    are filtered downstream by the default-deal stage gate in
    _resolve_ticket_deals (must be Proposta Aceita or Ganho).

    Full-fetch every run — apólice stage transitions don't bump the ticket's
    hs_lastmodifieddate, so an incremental cursor would silently miss them.
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


def _resolve_ticket_deals(client, tickets, summary):
    """Phase 2 — for each ticket, identify (apólice, default_deal) pair.

    Selection rules:
    - ticket-level benefit: beneficio_a_ser_cotado must be in
      VALID_BENEFITS_HUBSPOT, otherwise the entire ticket is skipped
      (invalid_benefit). Benefit lives on the ticket, not the apólice.
    - apólice deal: pipeline=APOLICE_PIPELINE_ID, current dealstage in
      APOLICE_VALID_STAGES (pré-ativação or later), AND entered pré-ativação
      >= 2024-09-01. If multiple match, first one is used and
      summary["skipped"]["multiple_apolices"] is bumped (warning, not skip).
    - default deal: pipeline=DEFAULT_DEAL_PIPELINE_ID AND dealstage in
      DEFAULT_DEAL_VALID_STAGES (Proposta Aceita / Ganho). First match used.
      The stage gate stands in for team-level filtering — non-Vendas tickets
      typically have a default deal stuck at an earlier stage.

    Tickets without a valid apólice OR without a default deal at the right
    stage are skipped. Returns dict {ticket_id: {"apolice": dict, "default_deal": dict}}.
    """
    if not tickets:
        return {}
    ticket_ids = [t["id"] for t in tickets]
    ticket_props_by_id = {t["id"]: t.get("properties", {}) for t in tickets}
    ticket_to_deals = client.batch_read_associations("tickets", "deals", ticket_ids)
    all_deal_ids = list({d for deals in ticket_to_deals.values() for d in deals})
    deal_props = client.batch_read_objects("deals", all_deal_ids, DEAL_PROPERTIES)

    out = {}
    for ticket_id in ticket_ids:
        t_props = ticket_props_by_id.get(ticket_id, {})
        if t_props.get("beneficio_a_ser_cotado") not in VALID_BENEFITS_HUBSPOT:
            summary["skipped"]["invalid_benefit"] += 1
            continue

        deals_for_ticket = ticket_to_deals.get(ticket_id, [])
        apolices_in_pre_ativacao = []
        default_deal = None
        for d in deals_for_ticket:
            props = deal_props.get(d, {})
            pipeline = props.get("pipeline")
            if pipeline == APOLICE_PIPELINE_ID:
                stage = props.get("dealstage")
                if stage not in APOLICE_VALID_STAGES:
                    continue
                # Deals that skipped pré-ativação (went straight to Ativação+)
                # won't have the date-entered property. Accept them only when
                # current stage is past pré-ativação; at pré-ativação itself,
                # missing date means the gate cannot be proven.
                entered = parse_date(props.get("hs_v2_date_entered_14038792"))
                if entered is None and stage == PRE_ATIVACAO_STAGE_ID:
                    continue
                if entered is not None and entered < PRE_ATIVACAO_DATE_FLOOR:
                    continue
                apolices_in_pre_ativacao.append({"id": d, "properties": props})
            elif pipeline == DEFAULT_DEAL_PIPELINE_ID:
                if props.get("dealstage") not in DEFAULT_DEAL_VALID_STAGES:
                    continue
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
        f"(valid benefit + apólice in pré-ativação + default deal)"
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
    benefit_raw = map_benefit_type(ticket_props.get("beneficio_a_ser_cotado"))
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

    Cascade (for deletable policies):
    - DELETE FROM commissions WHERE policy_id IN (...)
    - DELETE FROM ev_validations WHERE policy_id IN (...)
    - UPDATE financial_imports SET policy_id = NULL, match_status = UNMATCHED
    - DELETE FROM policies WHERE id IN (...)

    Includes is_locked rows — edit-lock prevents overwrite during upsert, not
    deletion when the source disappears.

    PAID HISTORY IS NEVER DELETED: a policy with any is_final commission, or
    a MATCHED financial import inside a LOCKED appraisal month, is the
    official record of money already paid. Archiving a ticket in HubSpot is
    routine CRM work and must not erase it. Such policies are preserved,
    auto-CANCELLED (cancelled policies are excluded from payable, projection
    and future apuração), stamped with sync_absent_since on the first
    disappearance, and surfaced in the summary for human review.

    Safety guard: if seen_ticket_ids is empty AND policies has rows, abort with
    an error in summary["errors"]. A zero-result fetch against a populated DB
    is more likely a HubSpot anomaly (silent pipeline change, expired token
    returning 200) than a real wipe.
    """
    from app.models import (
        Commission, EvValidation, FinancialImport, Appraisal, AppraisalStatus,
        CommissionStatus,
    )

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

    protected_ids = {
        pid
        for (pid,) in db.session.query(Commission.policy_id).filter(
            Commission.policy_id.in_(absent_ids),
            Commission.is_final.is_(True),
        ).distinct().all()
    }
    locked_pairs = {
        (a.month, a.year)
        for a in Appraisal.query.filter_by(status=AppraisalStatus.LOCKED).all()
    }
    if locked_pairs:
        matched_rows = db.session.query(
            FinancialImport.policy_id,
            FinancialImport.month,
            FinancialImport.year,
        ).filter(
            FinancialImport.policy_id.in_(absent_ids),
            FinancialImport.match_status == 'MATCHED',
        ).distinct().all()
        protected_ids.update(
            pid for pid, m, y in matched_rows if (m, y) in locked_pairs
        )

    preserved = [p for p in absent if p.id in protected_ids]
    deletable_ids = [p.id for p in absent if p.id not in protected_ids]

    for p in preserved:
        if p.sync_absent_since is None:
            p.sync_absent_since = datetime.now(timezone.utc)
        p.commission_status = CommissionStatus.CANCELLED

    if preserved:
        summary["preserved_locked"] = len(preserved)
        summary["preserved_locked_tickets"] = sorted(
            p.hubspot_ticket_id for p in preserved
        )
        logger.warning(
            "Delete-by-absence: %d policy(ies) com histórico pago (LOCKED) "
            "sumiram do HubSpot e foram PRESERVADAS + canceladas para revisão "
            "humana: %s",
            len(preserved),
            ", ".join(summary["preserved_locked_tickets"]),
        )

    if deletable_ids:
        Commission.query.filter(
            Commission.policy_id.in_(deletable_ids)
        ).delete(synchronize_session=False)
        EvValidation.query.filter(
            EvValidation.policy_id.in_(deletable_ids)
        ).delete(synchronize_session=False)
        # Reset the match cleanly — a MATCHED row pointing at no policy would
        # corrupt the paid-totals recompute and the review screens.
        FinancialImport.query.filter(
            FinancialImport.policy_id.in_(deletable_ids)
        ).update(
            {
                FinancialImport.policy_id: None,
                FinancialImport.match_status: 'UNMATCHED',
                FinancialImport.matched_at: None,
            },
            synchronize_session=False,
        )
        Policy.query.filter(Policy.id.in_(deletable_ids)).delete(synchronize_session=False)

    summary["deleted"] = len(deletable_ids)
    logger.info(
        f"Delete-by-absence: {len(deletable_ids)} policies removidas "
        f"(commissions/ev_validations cascateadas, financial_imports unlinked), "
        f"{len(preserved)} preservadas por histórico pago"
    )


# --- Orchestrator ---

def _new_summary():
    return {
        "timestamp": None,
        "created": 0,
        "updated": 0,
        "deleted": 0,
        "preserved_locked": 0,
        "preserved_locked_tickets": [],
        "skipped": {
            "invalid_benefit": 0,
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
    PlatformSetting.set(
        "hubspot_last_sync_preserved_locked",
        summary.get("preserved_locked", 0), user_id=None,
    )
    PlatformSetting.set(
        "hubspot_last_sync_preserved_locked_tickets",
        summary.get("preserved_locked_tickets", []), user_id=None,
    )
    skipped = summary["skipped"] if isinstance(summary["skipped"], dict) else {}
    skipped_total = sum(skipped.values()) if skipped else (summary["skipped"] or 0)
    PlatformSetting.set("hubspot_last_sync_skipped", skipped_total, user_id=None)
    # Persist the breakdown so admins can see WHY tickets dropped without
    # tailing logs — gap diagnostics (e.g. "expected 100+, got 30") need this.
    PlatformSetting.set("hubspot_last_sync_skipped_breakdown", skipped, user_id=None)
    db.session.commit()


def run_sync():
    """Main sync job: pull tickets matching gating criteria, resolve their
    apólice + default deals, and upsert into `policies`. Then delete any
    policies whose ticket id is no longer in the HubSpot result set.

    Serialized across processes by a Postgres advisory lock — every gunicorn
    worker runs its own scheduler, so without it each cron tick fired N
    concurrent syncs (IntegrityError on clients, deadlocks on policies,
    rollbacks discarding sibling upserts). The loser is a clean no-op.

    Returns summary dict, or {"skipped": "already_running"} when another
    sync holds the lock.
    """
    from app.modules.locks import try_advisory_lock, HUBSPOT_SYNC_LOCK

    with try_advisory_lock(HUBSPOT_SYNC_LOCK) as got:
        if not got:
            logger.info("HubSpot sync skipped: another sync is already running")
            return {"skipped": "already_running"}
        return _run_sync_locked()


def _run_sync_locked():
    client = HubSpotClient()
    summary = _new_summary()

    # Match EVs against the platform's full user list (active + inactive).
    # Historical apólices owned by deactivated EVs must keep syncing —
    # otherwise their commissions/validations silently drift out of sync.
    from app.models import UserRole
    evs = User.query.filter(
        User.role.in_([UserRole.EV, UserRole.CN]),
    ).all()
    ev_lookup = _build_ev_lookup(evs)
    ev_name_lookup = _build_ev_name_lookup(evs)
    logger.info(f"EVs in platform (active + inactive): {len(ev_lookup)}")

    if not ev_lookup:
        logger.warning("No EVs found in platform — nothing to sync")
        summary["timestamp"] = datetime.now(timezone.utc).isoformat()
        summary["errors"].append("No EVs in platform")
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
            logger.warning(f"hubspot_owner_map: {oid}→{email!r} doesn't match any EV in platform")
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
            "Skipped %d ticket(s) with no matching EV. "
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
