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
from app.modules.hubspot_sync.sync import _process_ticket, _build_ev_lookup, _build_ev_name_lookup, _normalize_owner_name


def _ev(email, name=None):
    u = User(email=email, name=name or email, role=UserRole.EV, active=True)
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

    ev_lookup = _build_ev_lookup([old_ev, new_ev])

    policy = Policy(
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

    _process_ticket(mock_client, ticket, {}, ev_lookup)
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

    ev_lookup = _build_ev_lookup([ev1, ev2])

    policy = Policy(
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

    _process_ticket(mock_client, ticket, {}, ev_lookup)
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

    ev_lookup = _build_ev_lookup([old_ev])

    policy = Policy(
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

    _process_ticket(mock_client, ticket, {}, ev_lookup)
    db.session.flush()
    db.session.refresh(policy)

    # Non-lockable: updated
    from decimal import Decimal
    assert policy.mrr_projected == Decimal("9999")
    # Lockable: preserved
    assert policy.closed_date == date(2025, 6, 1)


def test_sync_matches_ev_by_name_fallback(db_session):
    """When email local-part doesn't match, the EV is resolved by full name."""
    # EV registered in platform with one email domain...
    ev = _ev("luciana.rodrigues@piposaude.com.br", name="Luciana Rodrigues")
    db.session.flush()

    ev_lookup = _build_ev_lookup([ev])
    ev_name_lookup = _build_ev_name_lookup([ev])

    policy = Policy(hubspot_ticket_id="NAME-T1")
    db.session.add(policy)
    db.session.flush()

    # ...but HubSpot stores a different email domain, so local-part won't match
    # if solicitante_demanda resolves to "luciana.rodrigues@outraempresa.com"
    # Here we simulate that by passing an owner_map where the ID maps to a
    # different email, but the name matches.
    owner_map = {
        "99": {"email": "luciana.rodrigues@outraempresa.com", "name": "Luciana Rodrigues"},
    }

    ticket = {
        "id": "NAME-T1",
        "properties": {
            "solicitante_demanda": "99",
            "cliente___nome_da_empresa": "Cliente Teste",
            "mrr___receita_mensal": "3000",
        },
    }

    mock_client = MagicMock()
    mock_client.get_associations.return_value = {"results": []}

    _process_ticket(mock_client, ticket, owner_map, ev_lookup, ev_name_lookup)
    db.session.flush()
    db.session.refresh(policy)

    assert policy.ev_id == ev.id


def test_sync_matches_ev_with_deactivation_suffix(db_session):
    """HubSpot appends '(usuario desativado/removido)' to deactivated owner names.
    The name-based fallback must still resolve to the platform EV after stripping the suffix."""
    ev = _ev("karina.gomes@piposaude.com.br", name="Karina Gomes")
    db.session.flush()

    ev_lookup = _build_ev_lookup([ev])
    ev_name_lookup = _build_ev_name_lookup([ev])

    policy = Policy(hubspot_ticket_id="DEACT-T1")
    db.session.add(policy)
    db.session.flush()

    # HubSpot returns the owner name with a deactivation suffix; email is empty
    owner_map = {
        "77": {"email": None, "name": "Karina Gomes (usuario desativado/removido)"},
    }

    ticket = {
        "id": "DEACT-T1",
        "properties": {
            "solicitante_demanda": "77",
            "cliente___nome_da_empresa": "Cliente X",
            "mrr___receita_mensal": "2000",
        },
    }

    mock_client = MagicMock()
    mock_client.get_associations.return_value = {"results": []}

    _process_ticket(mock_client, ticket, owner_map, ev_lookup, ev_name_lookup)
    db.session.flush()
    db.session.refresh(policy)

    assert policy.ev_id == ev.id


def test_normalize_owner_name_strips_suffix():
    assert _normalize_owner_name("Karina Gomes (usuario desativado/removido)") == "karina gomes"
    assert _normalize_owner_name("Bruno Fernandes") == "bruno fernandes"
    assert _normalize_owner_name("Milena Vançan (deactivated)") == "milena vançan"
    assert _normalize_owner_name(None) == ""
    assert _normalize_owner_name("") == ""
