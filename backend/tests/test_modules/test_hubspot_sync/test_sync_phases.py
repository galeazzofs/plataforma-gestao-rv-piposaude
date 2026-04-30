"""Tests for individual phases of the apolice-anchored sync."""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.modules.hubspot_sync.sync import (
    _fetch_apolices,
    APOLICE_PIPELINE_ID,
    VALID_BENEFITS_HUBSPOT,
    APOLICE_PROPERTIES,
)


def test_fetch_apolices_builds_correct_search_filters():
    client = MagicMock()
    client.search_deals.return_value = {"results": [], "paging": {}}

    _fetch_apolices(client)

    client.search_deals.assert_called_once()
    call_kwargs = client.search_deals.call_args.kwargs
    filters = call_kwargs["filters"]
    # 2 filters AND-ed: pipeline + benefit IN list
    pipeline_filter = next(f for f in filters if f["propertyName"] == "hs_pipeline")
    assert pipeline_filter["operator"] == "EQ"
    assert pipeline_filter["value"] == APOLICE_PIPELINE_ID

    benefit_filter = next(f for f in filters if f["propertyName"] == "apolice___beneficio")
    assert benefit_filter["operator"] == "IN"
    assert set(benefit_filter["values"]) == set(VALID_BENEFITS_HUBSPOT)

    assert set(call_kwargs["properties"]) == set(APOLICE_PROPERTIES)


def test_fetch_apolices_paginates_until_exhausted():
    client = MagicMock()
    client.search_deals.side_effect = [
        {"results": [{"id": "A1"}, {"id": "A2"}], "paging": {"next": {"after": "cursor"}}},
        {"results": [{"id": "A3"}], "paging": {}},
    ]
    apolices = _fetch_apolices(client)
    assert [a["id"] for a in apolices] == ["A1", "A2", "A3"]
    assert client.search_deals.call_count == 2
    # Second call passes the cursor
    assert client.search_deals.call_args_list[1].kwargs["after"] == "cursor"


def test_fetch_apolices_empty_first_page_returns_empty():
    client = MagicMock()
    client.search_deals.return_value = {"results": [], "paging": {}}
    assert _fetch_apolices(client) == []


# Task 8: _fetch_apolice_tickets
from app.modules.hubspot_sync.sync import _fetch_apolice_tickets


def test_fetch_apolice_tickets_returns_first_ticket_per_apolice():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "A1": ["T1"],
        "A2": ["T2", "T2-extra"],  # multiple tickets — take first, log warn
    }
    summary = {"skipped": {"no_ticket": 0}}
    apolices = [{"id": "A1"}, {"id": "A2"}, {"id": "A3"}]

    result = _fetch_apolice_tickets(client, apolices, summary)

    assert result == {"A1": "T1", "A2": "T2"}
    # A3 had no associations
    assert summary["skipped"]["no_ticket"] == 1
    client.batch_read_associations.assert_called_once_with("deals", "tickets", ["A1", "A2", "A3"])


def test_fetch_apolice_tickets_empty_input():
    client = MagicMock()
    summary = {"skipped": {"no_ticket": 0}}
    result = _fetch_apolice_tickets(client, [], summary)
    assert result == {}
    assert summary["skipped"]["no_ticket"] == 0


# Task 9: _fetch_and_validate_tickets
from app.modules.hubspot_sync.sync import _fetch_and_validate_tickets


def _ticket_props(pipeline=None, stage=None, closed_date=None):
    """Helper: build ticket properties with defaults for valid-ticket fields."""
    return {
        "hs_pipeline": pipeline if pipeline is not None else "651307",
        "hs_pipeline_stage": stage if stage is not None else "11947921",
        "closed_date": closed_date if closed_date is not None else "2025-06-01T00:00:00Z",
        "mrr___receita_mensal": "1000",
        "solicitante_demanda": "ev@x",
        "cliente___nome_da_empresa": "ClientCo",
        "cotar___segmentacao_pipo": "M",
    }


def _new_summary():
    return {"skipped": {"no_ticket": 0, "wrong_pipeline": 0,
                        "not_gongo": 0, "too_old": 0, "no_default_deal": 0}}


def test_validate_tickets_keeps_valid():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(),
        "T2": _ticket_props(),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1", "T2"], summary)
    assert set(result.keys()) == {"T1", "T2"}
    # batch_read_objects was called with TICKET_PROPERTIES
    call = client.batch_read_objects.call_args
    assert call.args[0] == "tickets"
    assert set(call.args[1]) == {"T1", "T2"}
    from app.modules.hubspot_sync.sync import TICKET_PROPERTIES
    assert call.args[2] == TICKET_PROPERTIES


def test_validate_tickets_drops_wrong_pipeline():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(pipeline="999999"),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["wrong_pipeline"] == 1


def test_validate_tickets_drops_wrong_stage():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(stage="555"),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["not_gongo"] == 1


def test_validate_tickets_drops_too_old():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(closed_date="2024-01-15T00:00:00Z"),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["too_old"] == 1


def test_validate_tickets_drops_missing_closed_date():
    client = MagicMock()
    client.batch_read_objects.return_value = {
        "T1": _ticket_props(closed_date=""),
    }
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, ["T1"], summary)
    assert result == {}
    assert summary["skipped"]["too_old"] == 1


def test_validate_tickets_empty_input():
    client = MagicMock()
    summary = _new_summary()
    result = _fetch_and_validate_tickets(client, [], summary)
    assert result == {}
    client.batch_read_objects.assert_not_called()


# Task 10: _filter_tickets_with_default_deal
from app.modules.hubspot_sync.sync import _filter_tickets_with_default_deal


def test_filter_tickets_keeps_those_with_default_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D1"],
        "T2": ["D2", "D3"],
    }
    client.batch_read_objects.return_value = {
        "D1": {"hs_pipeline": "default"},
        "D2": {"hs_pipeline": "999999"},  # not default
        "D3": {"hs_pipeline": "default"},
    }
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, ["T1", "T2"], summary)
    assert result == {"T1", "T2"}  # T2 has at least one default deal
    assert summary["skipped"]["no_default_deal"] == 0


def test_filter_tickets_drops_those_without_default_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D1"],
    }
    client.batch_read_objects.return_value = {
        "D1": {"hs_pipeline": "999999"},
    }
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, ["T1"], summary)
    assert result == set()
    assert summary["skipped"]["no_default_deal"] == 1


def test_filter_tickets_drops_those_without_any_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {}  # T1 has no deals
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, ["T1"], summary)
    assert result == set()
    assert summary["skipped"]["no_default_deal"] == 1


def test_filter_tickets_empty_input():
    client = MagicMock()
    summary = _new_summary()
    result = _filter_tickets_with_default_deal(client, [], summary)
    assert result == set()
    client.batch_read_associations.assert_not_called()


# Task 11: _upsert_policy
from app.extensions import db
from app.models import User, UserRole, Policy, Client, Segment, BenefitType
from app.modules.hubspot_sync.sync import _upsert_policy


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _apolice(apolice_id, beneficio="Saúde", numero="AP-001", parceiro="Bradesco"):
    return {
        "id": apolice_id,
        "properties": {
            "apolice___beneficio": beneficio,
            "numero_apolice": numero,
            "parceiro": parceiro,
        },
    }


def _ticket(ev_email="ev@x", client_name="ClientCo", mrr="1500",
            closed="2025-06-01T00:00:00Z", segment="M"):
    return {
        "solicitante_demanda": ev_email,
        "cliente___nome_da_empresa": client_name,
        "mrr___receita_mensal": mrr,
        "closed_date": closed,
        "cotar___segmentacao_pipo": segment,
        "hs_pipeline": "651307",
        "hs_pipeline_stage": "11947921",
    }


def test_upsert_creates_new_policy(db_session):
    ev = _ev("ev@x")
    owner_map = {}  # solicitante_demanda is already an email here
    apolice = _apolice("A1", beneficio="Saúde", numero="AP-001", parceiro="Bradesco")
    ticket = _ticket(ev_email="ev@x", client_name="Acme", mrr="2500")

    is_new = _upsert_policy(apolice, ticket, owner_map, ticket_id="T1")
    db.session.flush()

    assert is_new is True
    policy = Policy.query.filter_by(hubspot_apolice_id="A1").one()
    assert policy.numero_apolice == "AP-001"
    assert policy.partner_operator == "Bradesco"
    assert policy.benefit_type == BenefitType.SAUDE
    assert policy.mrr_projected == Decimal("2500")
    assert policy.ev_id == ev.id
    assert policy.client.name == Client.find_or_create("Acme").name
    assert policy.segment == Segment.M
    assert policy.closed_date == date(2025, 6, 1)


def test_upsert_updates_existing_policy(db_session):
    ev = _ev("ev2@x")
    owner_map = {}
    existing = Policy(
        hubspot_apolice_id="A2",
        hubspot_ticket_id="T2",
        ev_id=ev.id,
        mrr_projected=Decimal("100"),
    )
    db.session.add(existing)
    db.session.flush()

    apolice = _apolice("A2", numero="AP-NEW")
    ticket = _ticket(ev_email="ev2@x", mrr="9999")

    is_new = _upsert_policy(apolice, ticket, owner_map, ticket_id="T2-NEW")
    db.session.flush()

    assert is_new is False
    db.session.refresh(existing)
    assert existing.mrr_projected == Decimal("9999")
    assert existing.numero_apolice == "AP-NEW"
    assert existing.hubspot_ticket_id == "T2-NEW"


def test_upsert_saude_e_odonto_maps_to_combined_enum(db_session):
    _ev("ev3@x")
    apolice = _apolice("A3", beneficio="Saúde e Odonto")
    ticket = _ticket(ev_email="ev3@x")
    _upsert_policy(apolice, ticket, {}, ticket_id="T3")
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_apolice_id="A3").one()
    assert policy.benefit_type == BenefitType.SAUDE_ODONTO


def test_upsert_multiple_apolices_same_ticket(db_session):
    _ev("ev4@x")
    ticket = _ticket(ev_email="ev4@x", mrr="3000")
    for apolice_id, beneficio in [("A4-S", "Saúde"), ("A4-O", "Odonto"), ("A4-V", "Vida")]:
        apolice = _apolice(apolice_id, beneficio=beneficio)
        _upsert_policy(apolice, ticket, {}, ticket_id="T4")
    db.session.flush()

    rows = Policy.query.filter_by(hubspot_ticket_id="T4").order_by(Policy.hubspot_apolice_id).all()
    assert len(rows) == 3
    assert {r.hubspot_apolice_id for r in rows} == {"A4-S", "A4-O", "A4-V"}
    assert {r.benefit_type for r in rows} == {BenefitType.SAUDE, BenefitType.ODONTO, BenefitType.VIDA}
    # All share the same MRR (replicated)
    assert {r.mrr_projected for r in rows} == {Decimal("3000")}


def test_upsert_respects_is_locked_for_lockable_fields(db_session):
    ev_old = _ev("locked-old@x")
    ev_new = _ev("locked-new@x")
    locked = Policy(
        hubspot_apolice_id="A-LOCK",
        hubspot_ticket_id="T-LOCK",
        ev_id=ev_old.id,
        segment=Segment.M,
        closed_date=date(2025, 1, 1),
        is_locked=True,
    )
    db.session.add(locked)
    db.session.flush()

    apolice = _apolice("A-LOCK", parceiro="NewOp")
    ticket = _ticket(ev_email="locked-new@x", segment="G", closed="2026-03-01T00:00:00Z", mrr="7777")
    _upsert_policy(apolice, ticket, {}, ticket_id="T-LOCK-NEW")
    db.session.flush()
    db.session.refresh(locked)

    # Lockable: preserved
    assert locked.ev_id == ev_old.id
    assert locked.segment == Segment.M
    assert locked.closed_date == date(2025, 1, 1)
    # Non-lockable: updated
    assert locked.mrr_projected == Decimal("7777")
    assert locked.partner_operator == "NewOp"
    assert locked.hubspot_ticket_id == "T-LOCK-NEW"


def test_upsert_resolves_ev_via_owner_map(db_session):
    ev = _ev("from-owner@x")
    owner_map = {"99999": "from-owner@x"}
    apolice = _apolice("A-OWN")
    ticket = _ticket(ev_email="99999")  # solicitante_demanda is an owner_id, not email
    _upsert_policy(apolice, ticket, owner_map, ticket_id="T-OWN")
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_apolice_id="A-OWN").one()
    assert policy.ev_id == ev.id
