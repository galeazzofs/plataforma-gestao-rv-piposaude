import logging
import re
from datetime import datetime, timezone
from app.extensions import db
from app.models import User, Policy, Client, PlatformSetting
from app.models.client import normalize_client_name
from app.modules.hubspot_sync.client import HubSpotClient
from app.modules.hubspot_sync.mapper import (
    map_segment, map_benefit_type, parse_date, parse_decimal,
)

logger = logging.getLogger(__name__)

TICKET_PROPERTIES = [
    "solicitante_demanda", "cotar___segmentacao_pipo",
    "mrr___receita_mensal", "closed_date",
    "apolice___beneficio", "parceiro",
    "cliente___nome_da_empresa",
]

DEAL_PROPERTIES = ["dealstage", "data_onboarding", "pipeline", "apolice___beneficio"]

APOLICES_PIPELINE = "2453678"

TICKET_IMPLANT_PROPERTIES = ["previsao_primeiro_pagamento", "mrr_pos_implantacao"]


def _email_local(email):
    """Return the local part of an email (before @)."""
    return email.split("@")[0].lower() if email else ""


def _normalize_owner_name(name):
    """Normalize a HubSpot owner name for matching.

    HubSpot appends suffixes like "(usuario desativado/removido)" to deactivated
    user names. Strip any trailing parenthetical before comparing to platform names.
    """
    if not name:
        return ""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip().lower()


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
    return {u.name.strip().lower(): u for u in active_evs}


def _resolve_owner_info(owner_map, owner_id_or_email):
    """Extract email and name from owner_map entry, with fallback.

    owner_map values are {email, name} dicts from get_all_owners().
    If the key isn't found, treat owner_id_or_email as an email directly.
    """
    info = owner_map.get(str(owner_id_or_email)) if owner_id_or_email else None
    if info:
        return info.get("email"), info.get("name") or ""
    # Fallback: the field may already contain an email
    return owner_id_or_email, ""


def run_sync():
    """Main sync job: pull gongoed tickets from HubSpot, upsert into policies.

    Only syncs tickets whose solicitante_demanda matches an active EV/CN
    user in the platform (matched by email local part to handle domain
    differences between HubSpot and the platform).
    Returns summary dict.
    """
    client = HubSpotClient()
    created = 0
    updated = 0
    skipped = 0
    errors = []

    # Pre-load active EV/CN users from our database
    from app.models import UserRole
    active_evs = User.query.filter(
        User.role.in_([UserRole.EV, UserRole.CN]),
        User.active.is_(True),
    ).all()
    ev_lookup = _build_ev_lookup(active_evs)
    ev_name_lookup = _build_ev_name_lookup(active_evs)
    logger.info(f"Active EVs in platform: {len(ev_lookup)} — {list(ev_lookup.keys())}")

    if not ev_lookup:
        logger.warning("No active EVs found — nothing to sync")
        return {"timestamp": datetime.now(timezone.utc).isoformat(),
                "created": 0, "updated": 0, "errors": ["No active EVs in platform"], "error_count": 1}

    # Load manual owner ID mapping for users fully deleted from HubSpot
    # Format: {"hubspot_owner_id": "platform_user_email"}
    raw_owner_map_setting = PlatformSetting.get("hubspot_owner_map") or {}
    ev_override_lookup = {}  # owner_id_str → User
    for oid, email in raw_owner_map_setting.items():
        local = _email_local(email)
        u = ev_lookup.get(local)
        if u:
            ev_override_lookup[str(oid)] = u
        else:
            logger.warning(f"hubspot_owner_map: {oid}→{email!r} doesn't match any active EV")
    if ev_override_lookup:
        logger.info(f"Manual owner overrides loaded: {list(ev_override_lookup.keys())}")

    # Pre-load owner map (owner_id → {email, name}) for EV resolution
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
    processed = 0
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
            # Skip tickets not belonging to active EVs
            props = ticket.get("properties", {})
            owner_id_or_email = props.get("solicitante_demanda")
            resolved_email, resolved_name = _resolve_owner_info(owner_map, owner_id_or_email)

            local = _email_local(resolved_email) if resolved_email else ""
            normalized_name = _normalize_owner_name(resolved_name)
            if local in ev_lookup:
                pass  # matched by email
            elif normalized_name and normalized_name in ev_name_lookup:
                pass  # matched by normalized name (strips deactivation suffixes)
            elif str(owner_id_or_email) in ev_override_lookup:
                pass  # matched by manual hubspot_owner_map setting
            else:
                skipped += 1
                logger.debug(
                    f"Skipped ticket {ticket.get('id')}: no EV match for "
                    f"owner={owner_id_or_email!r} email={resolved_email!r} name={resolved_name!r}"
                )
                continue

            try:
                was_created = _process_ticket(
                    client, ticket, owner_map, ev_lookup, ev_name_lookup, ev_override_lookup
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
                processed += 1
                if processed % 50 == 0:
                    db.session.commit()
                    logger.info(f"Sync progress: {processed} tickets processed ({created} created, {updated} updated)")
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

    logger.info(f"Sync finished: {created} created, {updated} updated, {skipped} skipped (not active EV)")

    timestamp = datetime.now(timezone.utc).isoformat()
    summary = {
        "timestamp": timestamp,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_count": len(errors),
    }

    PlatformSetting.set("hubspot_last_sync", timestamp, user_id=None)
    PlatformSetting.set("hubspot_last_sync_errors", errors, user_id=None)
    PlatformSetting.set("hubspot_last_sync_created", created, user_id=None)
    PlatformSetting.set("hubspot_last_sync_updated", updated, user_id=None)
    db.session.commit()

    logger.info(f"HubSpot sync completed: {summary}")
    return summary


def _process_ticket(hs_client, ticket, owner_map=None, ev_lookup=None, ev_name_lookup=None, ev_override_lookup=None):
    """Process a single HubSpot ticket into a policy. Returns True if created.

    Respects Policy.is_locked: when set, lockable fields (ev_id, client_id,
    segment, closed_date, first_payment_real, initial_installments_paid,
    partner_operator) are NOT overwritten. Non-lockable fields (mrr_projected,
    benefit_type, deal_*) are always updated.
    """
    owner_map = owner_map or {}
    ev_lookup = ev_lookup or {}
    ev_name_lookup = ev_name_lookup or {}
    ev_override_lookup = ev_override_lookup or {}
    props = ticket.get("properties", {})
    ticket_id = ticket["id"]

    # Resolve EV: solicitante_demanda → owner_id → email/name/override → User
    owner_id_or_email = props.get("solicitante_demanda")
    ev_email, ev_owner_name = _resolve_owner_info(owner_map, owner_id_or_email)
    ev = ev_lookup.get(_email_local(ev_email)) if ev_email else None
    if ev is None and ev_owner_name:
        ev = ev_name_lookup.get(_normalize_owner_name(ev_owner_name))
    if ev is None and owner_id_or_email:
        ev = ev_override_lookup.get(str(owner_id_or_email))

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
        partner = props.get("parceiro")
        if partner:
            policy.partner_operator = partner.strip()

    # Non-lockable fields — always update
    ticket_benefit = map_benefit_type(props.get("apolice___beneficio"))
    policy.benefit_type = ticket_benefit  # may be overridden by deal below
    policy.mrr_projected = parse_decimal(props.get("mrr___receita_mensal"))

    # Fetch deal associations (non-lockable — always refresh)
    # A ticket may be associated with deals in multiple pipelines;
    # we prefer the deal in the Apólices pipeline for deploy_date.
    try:
        assoc = hs_client.get_associations("tickets", ticket_id, "deals")
        deal_ids = [r["toObjectId"] for r in assoc.get("results", [])]
        if deal_ids:
            # Find the deal in the Apólices pipeline; fall back to first deal
            chosen_deal_id = deal_ids[0]
            deal_props = {}
            for did in deal_ids:
                d = hs_client.get_deal(did, DEAL_PROPERTIES)
                d_props = d.get("properties", {})
                if d_props.get("pipeline") == APOLICES_PIPELINE:
                    chosen_deal_id = did
                    deal_props = d_props
                    break
                if not deal_props:
                    # Keep first deal as fallback
                    chosen_deal_id = did
                    deal_props = d_props

            policy.deal_id = str(chosen_deal_id)
            policy.deal_stage = deal_props.get("dealstage")
            if not locked:
                policy.deploy_date = parse_date(deal_props.get("data_onboarding"))
            # Use deal's benefit type as fallback when ticket has none
            if not ticket_benefit:
                deal_benefit = map_benefit_type(deal_props.get("apolice___beneficio"))
                if deal_benefit:
                    policy.benefit_type = deal_benefit

            # Navigate deal → tickets to find implantation ticket (spec §3.5)
            try:
                ticket_assocs = hs_client.get_associations(
                    "deals", chosen_deal_id, "tickets"
                )
                assoc_ticket_ids = [
                    str(r["toObjectId"])
                    for r in ticket_assocs.get("results", [])
                ]
                implant_ids = [
                    tid for tid in assoc_ticket_ids if tid != str(ticket_id)
                ]
                if implant_ids and not locked:
                    implant = hs_client.get_ticket(
                        implant_ids[0], TICKET_IMPLANT_PROPERTIES
                    )
                    impl_props = implant.get("properties", {})
                    policy.first_payment_prev = parse_date(
                        impl_props.get("previsao_primeiro_pagamento")
                    )
                    policy.mrr_post_deploy = parse_decimal(
                        impl_props.get("mrr_pos_implantacao")
                    )
            except Exception as e:
                logger.warning(
                    f"Implant ticket fetch failed for ticket {ticket_id}: {e}"
                )
    except Exception as e:
        logger.warning(f"Deal association fetch failed for ticket {ticket_id}: {e}")

    db.session.flush()
    return is_new
