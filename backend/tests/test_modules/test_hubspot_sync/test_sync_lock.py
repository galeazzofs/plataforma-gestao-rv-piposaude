"""Tests for HubSpot sync respecting Policy.is_locked.

When is_locked=True, fields ev_id, closed_date, segment, and client_id
must NOT be overwritten by the sync. Non-lockable fields like mrr_projected,
partner_operator, numero_apolice, and benefit_type are still updated.
"""
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
)
from app.modules.hubspot_sync.sync import _upsert_policy


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _apolice(apolice_id, beneficio="ODONTO", parceiro="OpA"):
    return {
        "id": apolice_id,
        "properties": {
            "apolice___beneficio": beneficio,
            "numero_apolice": f"AP-{apolice_id}",
            "parceiro": parceiro,
        },
    }


def _ticket_props(ev_email, client_name, segment="G", mrr="5000",
                  closed="2026-01-15T00:00:00Z"):
    return {
        "solicitante_demanda": ev_email,
        "cliente___nome_da_empresa": client_name,
        "cotar___segmentacao_pipo": segment,
        "mrr___receita_mensal": mrr,
        "closed_date": closed,
        "hs_pipeline": "651307",
        "hs_pipeline_stage": "11947921",
    }


def test_sync_preserves_locked_fields(db_session):
    """A locked policy keeps its ev_id, closed_date, segment, and client_id
    intact when the sync re-processes its apolice with different values."""
    old_ev = _ev("old-ev@x")
    _ev("new-ev@x")
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
    ticket = _ticket_props(ev_email="new-ev@x", client_name="NewClient",
                           segment="G", closed="2026-01-15T00:00:00Z")

    _upsert_policy(apolice, ticket, {}, ticket_id="LOCK-T1")
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
        ev_id=ev2.id,  # will be re-resolved
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 6, 1),
        is_locked=False,
    )
    db.session.add(policy)
    db.session.flush()

    apolice = _apolice("UNLOCK-A1", beneficio="Odonto")
    ticket = _ticket_props(ev_email="unlocked-ev2@x", client_name="SomeClient",
                           segment="G", closed="2026-01-15T00:00:00Z")

    _upsert_policy(apolice, ticket, {}, ticket_id="UNLOCK-T1")
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
    ticket = _ticket_props(ev_email="mrr-ev@x", client_name="MrrClient",
                           mrr="9999", closed="2026-02-01T00:00:00Z")

    _upsert_policy(apolice, ticket, {}, ticket_id="MRR-T1")
    db.session.flush()
    db.session.refresh(policy)

    # Non-lockable: updated
    assert policy.mrr_projected == Decimal("9999")
    assert policy.partner_operator == "NewPartner"
    # Lockable: preserved
    assert policy.closed_date == date(2025, 6, 1)
