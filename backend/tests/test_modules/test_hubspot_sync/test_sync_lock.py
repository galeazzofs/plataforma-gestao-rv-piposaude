"""Tests for HubSpot sync respecting Policy.is_locked + EV resolution.

When is_locked=True, fields ev_id, closed_date, segment, and client_id
must NOT be overwritten by the sync. Non-lockable fields like mrr_projected,
partner_operator, numero_apolice, hubspot_apolice_id, and benefit_type are
still updated.

EV resolution cascade (when ev_lookup/ev_name_lookup are provided):
  email local part → normalized owner name → manual owner_id override.
"""
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
)
from app.modules.hubspot_sync.sync import (
    _upsert_policy, _build_ev_lookup, _build_ev_name_lookup,
    _normalize_owner_name,
)


def _ev(email, name=None):
    u = User(email=email, name=name or email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _apolice(apolice_id, beneficio="Odonto", parceiro="OpA"):
    return {
        "id": apolice_id,
        "properties": {
            "apolice___beneficio": beneficio,
            "numero_apolice": f"AP-{apolice_id}",
            "parceiro": parceiro,
        },
    }


def _default_deal(closedate="2026-01-15T00:00:00Z", deal_id="D-DEFAULT"):
    return {"id": deal_id, "properties": {"closedate": closedate}}


def _ticket_props(ev_email, client_name, segment="G", mrr="5000"):
    return {
        "solicitante_demanda": ev_email,
        "cliente___nome_da_empresa": client_name,
        "cotar___segmentacao_pipo": segment,
        "mrr___receita_mensal": mrr,
        "hs_pipeline": "651307",
        "hs_pipeline_stage": "11947921",
        "time_solicitante": "Vendas",
    }


def test_sync_preserves_locked_fields(db_session):
    """A locked policy keeps its ev_id, closed_date, segment, and client_id
    intact when the sync re-processes its ticket with different values."""
    old_ev = _ev("old-ev@x")
    new_ev = _ev("new-ev@x")
    old_client = Client.find_or_create("OldClient")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="LOCK-A1",
        hubspot_ticket_id="LOCK-T1",
        ev_id=old_ev.id,
        client_id=old_client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 6, 1),
        is_locked=True,
    )
    db.session.add(policy)
    db.session.flush()

    apolice = _apolice("LOCK-A1", beneficio="Odonto")
    deal = _default_deal(closedate="2026-01-15T00:00:00Z")
    ticket = _ticket_props(ev_email="new-ev@x", client_name="NewClient", segment="G")

    _upsert_policy("LOCK-T1", ticket, apolice, deal, {})
    db.session.flush()
    db.session.refresh(policy)

    # Lockable fields preserved
    assert policy.ev_id == old_ev.id
    assert policy.client_id == old_client.id
    assert policy.segment == Segment.M
    assert policy.closed_date == date(2025, 6, 1)
    # Non-lockable: updated
    assert policy.benefit_type == BenefitType.ODONTO


def test_sync_updates_unlocked_policy_normally(db_session):
    _ev("unlocked-ev1@x")
    ev2 = _ev("unlocked-ev2@x")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="UNLOCK-A1",
        hubspot_ticket_id="UNLOCK-T1",
        ev_id=ev2.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 6, 1),
        is_locked=False,
    )
    db.session.add(policy)
    db.session.flush()

    apolice = _apolice("UNLOCK-A1", beneficio="Odonto")
    deal = _default_deal(closedate="2026-01-15T00:00:00Z")
    ticket = _ticket_props(ev_email="unlocked-ev2@x", client_name="SomeClient", segment="G")

    _upsert_policy("UNLOCK-T1", ticket, apolice, deal, {})
    db.session.flush()
    db.session.refresh(policy)

    assert policy.ev_id == ev2.id
    assert policy.closed_date == date(2026, 1, 15)
    assert policy.segment == Segment.G


def test_sync_updates_non_lockable_fields_on_locked_policy(db_session):
    old_ev = _ev("mrr-ev@x")
    old_client = Client.find_or_create("MrrClient")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="MRR-A1",
        hubspot_ticket_id="MRR-T1",
        ev_id=old_ev.id,
        client_id=old_client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 6, 1),
        mrr_projected=None,
        is_locked=True,
    )
    db.session.add(policy)
    db.session.flush()

    apolice = _apolice("MRR-A1", beneficio="Saúde", parceiro="NewPartner")
    deal = _default_deal(closedate="2026-02-01T00:00:00Z")
    ticket = _ticket_props(ev_email="mrr-ev@x", client_name="MrrClient", mrr="9999")

    _upsert_policy("MRR-T1", ticket, apolice, deal, {})
    db.session.flush()
    db.session.refresh(policy)

    # Non-lockable: updated
    assert policy.mrr_projected == Decimal("9999")
    assert policy.partner_operator == "NewPartner"
    # Lockable: preserved
    assert policy.closed_date == date(2025, 6, 1)


def test_sync_matches_ev_by_name_fallback(db_session):
    """When email local-part doesn't match, the EV is resolved by full name."""
    ev = _ev("luciana.rodrigues@piposaude.com.br", name="Luciana Rodrigues")
    db.session.flush()

    ev_lookup = _build_ev_lookup([ev])
    ev_name_lookup = _build_ev_name_lookup([ev])

    owner_map = {
        "99": {"email": "luciana.rodrigues@outraempresa.com", "name": "Luciana Rodrigues"},
    }

    apolice = _apolice("NAME-A1", beneficio="Saúde")
    deal = _default_deal(closedate="2026-01-15T00:00:00Z")
    ticket = _ticket_props(ev_email="99", client_name="Cliente Teste", mrr="3000")

    _upsert_policy(
        "NAME-T1", ticket, apolice, deal, owner_map,
        ev_lookup=ev_lookup, ev_name_lookup=ev_name_lookup,
    )
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_ticket_id="NAME-T1").one()
    assert policy.ev_id == ev.id


def test_sync_matches_ev_with_deactivation_suffix(db_session):
    """HubSpot appends '(usuario desativado/removido)' to deactivated owner names.
    The name-based fallback must still resolve after stripping the suffix."""
    ev = _ev("karina.gomes@piposaude.com.br", name="Karina Gomes")
    db.session.flush()

    ev_lookup = _build_ev_lookup([ev])
    ev_name_lookup = _build_ev_name_lookup([ev])

    owner_map = {
        "77": {"email": None, "name": "Karina Gomes (usuario desativado/removido)"},
    }

    apolice = _apolice("DEACT-A1", beneficio="Saúde")
    deal = _default_deal(closedate="2026-01-15T00:00:00Z")
    ticket = _ticket_props(ev_email="77", client_name="Cliente X", mrr="2000")

    _upsert_policy(
        "DEACT-T1", ticket, apolice, deal, owner_map,
        ev_lookup=ev_lookup, ev_name_lookup=ev_name_lookup,
    )
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_ticket_id="DEACT-T1").one()
    assert policy.ev_id == ev.id


def test_sync_skips_ticket_when_no_active_ev_matches(db_session):
    """When ev_lookup is provided and the cascade fails, _upsert_policy returns
    None and does not create the policy."""
    _ev("only-this-one@x")
    db.session.flush()

    ev_lookup = _build_ev_lookup(User.query.filter_by(active=True).all())
    ev_name_lookup = _build_ev_name_lookup(User.query.filter_by(active=True).all())

    apolice = _apolice("SKIP-A1", beneficio="Saúde")
    deal = _default_deal()
    ticket = _ticket_props(ev_email="someone-not-in-platform@x",
                           client_name="Cliente Y", mrr="1000")

    result = _upsert_policy(
        "SKIP-T1", ticket, apolice, deal, {},
        ev_lookup=ev_lookup, ev_name_lookup=ev_name_lookup,
    )
    db.session.flush()
    assert result is None
    assert Policy.query.filter_by(hubspot_ticket_id="SKIP-T1").first() is None


def test_normalize_owner_name_strips_suffix():
    assert _normalize_owner_name("Karina Gomes (usuario desativado/removido)") == "karina gomes"
    assert _normalize_owner_name("Bruno Fernandes") == "bruno fernandes"
    assert _normalize_owner_name("Milena Vançan (deactivated)") == "milena vancan"
    assert _normalize_owner_name(None) == ""
    assert _normalize_owner_name("") == ""
