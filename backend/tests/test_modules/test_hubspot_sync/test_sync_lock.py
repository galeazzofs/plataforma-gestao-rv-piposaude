"""Tests for HubSpot sync respecting Policy.is_locked.

When is_locked=True, fields ev_id, closed_date, segment, and client_id
must NOT be overwritten by the sync. Non-lockable fields like mrr_projected,
deal_id, and deal_stage are still updated regardless.
"""
from datetime import date
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
)
from app.modules.hubspot_sync.sync import _process_ticket


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def test_sync_preserves_locked_fields(db_session):
    """A locked policy keeps its ev_id, closed_date, segment, and client_id
    intact when the sync re-processes its ticket with different values."""
    # Original state
    old_ev = _ev("old-ev@x")
    new_ev = _ev("new-ev@x")
    old_client = Client.find_or_create("OldClient")
    new_client_name = "NewClient"
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-LOCK-T1",
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

    # HubSpot returns different values
    ticket = {
        "id": "LOCK-T1",
        "properties": {
            "solicitante_demanda": "new-ev@x",
            "cliente___nome_da_empresa": new_client_name,
            "cotar___segmentacao_pipo": "G",  # would map to Segment.G
            "apolice___beneficio": "ODONTO",
            "mrr___receita_mensal": "5000",
            "closed_date": "2026-01-15",
        },
    }

    mock_client = MagicMock()
    mock_client.get_associations.return_value = {"results": []}

    _process_ticket(mock_client, ticket, {})
    db.session.flush()
    db.session.refresh(policy)

    # Lockable fields preserved
    assert policy.ev_id == old_ev.id
    assert policy.client_id == old_client.id
    assert policy.segment == Segment.M
    assert policy.closed_date == date(2025, 6, 1)


def test_sync_updates_unlocked_policy_normally(db_session):
    """Unlocked policies get all fields updated from HubSpot."""
    ev1 = _ev("unlocked-ev1@x")
    ev2 = _ev("unlocked-ev2@x")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-UNLOCK-T1",
        hubspot_ticket_id="UNLOCK-T1",
        ev_id=ev1.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 6, 1),
        is_locked=False,
    )
    db.session.add(policy)
    db.session.flush()

    ticket = {
        "id": "UNLOCK-T1",
        "properties": {
            "solicitante_demanda": "unlocked-ev2@x",
            "cliente___nome_da_empresa": "SomeClient",
            "cotar___segmentacao_pipo": "G",
            "apolice___beneficio": "ODONTO",
            "mrr___receita_mensal": "5000",
            "closed_date": "2026-01-15",
        },
    }

    mock_client = MagicMock()
    mock_client.get_associations.return_value = {"results": []}

    _process_ticket(mock_client, ticket, {})
    db.session.flush()
    db.session.refresh(policy)

    # Ev updated to the new one
    assert policy.ev_id == ev2.id
    assert policy.closed_date == date(2026, 1, 15)


def test_sync_updates_non_lockable_fields_on_locked_policy(db_session):
    """Even when is_locked=True, mrr_projected and deal_* are still updated."""
    old_ev = _ev("mrr-ev@x")
    old_client = Client.find_or_create("MrrClient")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-MRR-T1",
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

    ticket = {
        "id": "MRR-T1",
        "properties": {
            "solicitante_demanda": "mrr-ev@x",  # same EV (locked anyway)
            "cliente___nome_da_empresa": "MrrClient",
            "mrr___receita_mensal": "9999",  # new mrr!
            "closed_date": "2026-02-01",  # different but locked
        },
    }

    mock_client = MagicMock()
    mock_client.get_associations.return_value = {"results": []}

    _process_ticket(mock_client, ticket, {})
    db.session.flush()
    db.session.refresh(policy)

    # Non-lockable: updated
    from decimal import Decimal
    assert policy.mrr_projected == Decimal("9999")
    # Lockable: preserved
    assert policy.closed_date == date(2025, 6, 1)
