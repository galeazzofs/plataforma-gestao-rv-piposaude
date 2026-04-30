"""Tests for individual phases of the ticket-anchored sync."""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.modules.hubspot_sync.sync import (
    _fetch_tickets,
    _resolve_ticket_apolices,
    _new_summary,
    APOLICE_PIPELINE_ID,
    PLACEMENT_PIPELINE_ID,
    GONGO_STAGE_ID,
    GONGO_DATE_FLOOR,
    DEFAULT_DEAL_PIPELINE_ID,
    VALID_BENEFITS_HUBSPOT,
    TICKET_PROPERTIES,
    DEAL_PROPERTIES,
)


# --- _fetch_tickets ---

def test_fetch_tickets_builds_correct_search_filters_full_fetch():
    client = MagicMock()
    client.search_tickets.return_value = {"results": [], "paging": {}}

    _fetch_tickets(client)

    client.search_tickets.assert_called_once()
    call_kwargs = client.search_tickets.call_args.kwargs
    filters = call_kwargs["filters"]
    # 3 filters AND-ed for full fetch (no incremental cursor)
    assert len(filters) == 3
    pipeline_f = next(f for f in filters if f["propertyName"] == "hs_pipeline")
    assert pipeline_f["operator"] == "EQ"
    assert pipeline_f["value"] == PLACEMENT_PIPELINE_ID

    stage_f = next(f for f in filters if f["propertyName"] == "hs_pipeline_stage")
    assert stage_f["operator"] == "EQ"
    assert stage_f["value"] == GONGO_STAGE_ID

    date_f = next(f for f in filters if f["propertyName"] == "closed_date")
    assert date_f["operator"] == "GTE"
    assert date_f["value"] == GONGO_DATE_FLOOR.isoformat()

    assert set(call_kwargs["properties"]) == set(TICKET_PROPERTIES)


def test_fetch_tickets_no_longer_accepts_since_argument():
    """_fetch_tickets perdeu o parâmetro `since` — full-fetch sempre."""
    import inspect
    from app.modules.hubspot_sync.sync import _fetch_tickets
    sig = inspect.signature(_fetch_tickets)
    assert "since" not in sig.parameters


def test_fetch_tickets_paginates_until_exhausted():
    client = MagicMock()
    client.search_tickets.side_effect = [
        {"results": [{"id": "T1"}, {"id": "T2"}], "paging": {"next": {"after": "cur"}}},
        {"results": [{"id": "T3"}], "paging": {}},
    ]
    tickets = _fetch_tickets(client)
    assert [t["id"] for t in tickets] == ["T1", "T2", "T3"]
    assert client.search_tickets.call_count == 2
    assert client.search_tickets.call_args_list[1].kwargs["after"] == "cur"


def test_fetch_tickets_empty_first_page_returns_empty():
    client = MagicMock()
    client.search_tickets.return_value = {"results": [], "paging": {}}
    assert _fetch_tickets(client) == []


# --- _resolve_ticket_apolices ---

def _new_summary():
    return {
        "skipped": {
            "no_default_deal": 0,
            "no_apolice": 0,
            "no_active_ev": 0,
            "not_pre_activation": 0,
        },
    }


def _ticket(tid):
    return {"id": tid, "properties": {}}


def test_resolve_ticket_apolices_keeps_ticket_with_valid_apolice_and_default():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-APOLICE", "D-DEFAULT"],
    }
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "numero_apolice": "AP-001",
            "parceiro": "Bradesco",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert "T1" in result
    assert len(result["T1"]) == 1
    assert result["T1"][0]["id"] == "D-APOLICE"
    assert result["T1"][0]["properties"]["apolice___beneficio"] == "Saúde"
    # Properties pulled from same batch_read — no extra round trip needed
    assert result["T1"][0]["properties"]["numero_apolice"] == "AP-001"
    # batch_read_objects was called with DEAL_PROPERTIES (single batch for both pipeline + apolice props)
    deal_call = client.batch_read_objects.call_args
    assert deal_call.args[0] == "deals"
    assert set(deal_call.args[2]) == set(DEAL_PROPERTIES)


def test_resolve_ticket_apolices_keeps_multiple_apolices_per_ticket():
    """A single ticket can drive multiple apolices (saúde + odonto)."""
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-S", "D-O", "D-DEFAULT"],
    }
    client.batch_read_objects.return_value = {
        "D-S": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
        "D-O": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Odonto",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert len(result["T1"]) == 2
    assert {a["id"] for a in result["T1"]} == {"D-S", "D-O"}


def test_resolve_ticket_apolices_drops_ticket_without_default_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-APOLICE"],  # no default
    }
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert result == {}
    assert summary["skipped"]["no_default_deal"] == 1


def test_resolve_ticket_apolices_drops_ticket_without_apolice():
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-DEFAULT"],  # default but no apolice
    }
    client.batch_read_objects.return_value = {
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert result == {}
    assert summary["skipped"]["no_apolice"] == 1


def test_resolve_ticket_apolices_drops_apolice_with_invalid_benefit():
    """Apolice deal in the right pipeline but with an unrecognised benefit
    is treated as if it didn't exist — ticket is dropped (no_apolice)."""
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-APOLICE", "D-DEFAULT"],
    }
    client.batch_read_objects.return_value = {
        "D-APOLICE": {"pipeline": APOLICE_PIPELINE_ID, "apolice___beneficio": "Outro"},
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert result == {}
    assert summary["skipped"]["no_apolice"] == 1


def test_resolve_ticket_apolices_drops_ticket_with_no_associated_deals():
    client = MagicMock()
    client.batch_read_associations.return_value = {}  # T1 has no deals at all
    client.batch_read_objects.return_value = {}
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert result == {}
    # No default deal → counted as no_default_deal
    assert summary["skipped"]["no_default_deal"] == 1


def test_resolve_ticket_apolices_empty_input():
    client = MagicMock()
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [], summary)

    assert result == {}
    client.batch_read_associations.assert_not_called()
    client.batch_read_objects.assert_not_called()


def test_resolve_ticket_apolices_includes_apolice_past_pre_activation():
    """Apólice com hs_v2_date_entered_14038792 >= 2024-09-01 é incluída."""
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-APOLICE", "D-DEFAULT"],
    }
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "numero_apolice": "AP-001",
            "parceiro": "Bradesco",
            "hs_v2_date_entered_14038792": "2025-01-15",
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert "T1" in result
    assert len(result["T1"]) == 1
    assert summary["skipped"]["not_pre_activation"] == 0


def test_resolve_ticket_apolices_skips_apolice_without_pre_activation_date():
    """Apólice sem hs_v2_date_entered_14038792 → skip + counter."""
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-APOLICE", "D-DEFAULT"],
    }
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "numero_apolice": "AP-001",
            "parceiro": "Bradesco",
            # hs_v2_date_entered_14038792 ausente
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    # Sem apólices válidas — ticket cai em no_apolice
    assert result == {}
    assert summary["skipped"]["not_pre_activation"] == 1
    assert summary["skipped"]["no_apolice"] == 1


def test_resolve_ticket_apolices_skips_apolice_with_pre_activation_before_floor():
    """Apólice com data anterior a 2024-09-01 → skip + counter."""
    client = MagicMock()
    client.batch_read_associations.return_value = {
        "T1": ["D-APOLICE", "D-DEFAULT"],
    }
    client.batch_read_objects.return_value = {
        "D-APOLICE": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "numero_apolice": "AP-001",
            "parceiro": "Bradesco",
            "hs_v2_date_entered_14038792": "2024-08-15",
        },
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }
    summary = _new_summary()

    result = _resolve_ticket_apolices(client, [_ticket("T1")], summary)

    assert result == {}
    assert summary["skipped"]["not_pre_activation"] == 1
    assert summary["skipped"]["no_apolice"] == 1


# --- _upsert_policy ---

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


def _ticket_for_upsert(ev_email="ev@x", client_name="ClientCo", mrr="1500",
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
    apolice = _apolice("A1", beneficio="Saúde", numero="AP-001", parceiro="Bradesco")
    ticket = _ticket_for_upsert(ev_email="ev@x", client_name="Acme", mrr="2500")

    is_new = _upsert_policy(apolice, ticket, {}, ticket_id="T1")
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
    existing = Policy(
        hubspot_apolice_id="A2",
        hubspot_ticket_id="T2",
        ev_id=ev.id,
        mrr_projected=Decimal("100"),
    )
    db.session.add(existing)
    db.session.flush()

    apolice = _apolice("A2", numero="AP-NEW")
    ticket = _ticket_for_upsert(ev_email="ev2@x", mrr="9999")

    is_new = _upsert_policy(apolice, ticket, {}, ticket_id="T2-NEW")
    db.session.flush()

    assert is_new is False
    db.session.refresh(existing)
    assert existing.mrr_projected == Decimal("9999")
    assert existing.numero_apolice == "AP-NEW"
    assert existing.hubspot_ticket_id == "T2-NEW"


def test_upsert_saude_e_odonto_maps_to_combined_enum(db_session):
    _ev("ev3@x")
    apolice = _apolice("A3", beneficio="Saúde e Odonto")
    ticket = _ticket_for_upsert(ev_email="ev3@x")
    _upsert_policy(apolice, ticket, {}, ticket_id="T3")
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_apolice_id="A3").one()
    assert policy.benefit_type == BenefitType.SAUDE_ODONTO


def test_upsert_multiple_apolices_same_ticket(db_session):
    _ev("ev4@x")
    ticket = _ticket_for_upsert(ev_email="ev4@x", mrr="3000")
    for apolice_id, beneficio in [("A4-S", "Saúde"), ("A4-O", "Odonto"), ("A4-V", "Vida")]:
        apolice = _apolice(apolice_id, beneficio=beneficio)
        _upsert_policy(apolice, ticket, {}, ticket_id="T4")
    db.session.flush()

    rows = Policy.query.filter_by(hubspot_ticket_id="T4").order_by(Policy.hubspot_apolice_id).all()
    assert len(rows) == 3
    assert {r.hubspot_apolice_id for r in rows} == {"A4-S", "A4-O", "A4-V"}
    assert {r.benefit_type for r in rows} == {BenefitType.SAUDE, BenefitType.ODONTO, BenefitType.VIDA}
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
    ticket = _ticket_for_upsert(ev_email="locked-new@x", segment="G", closed="2026-03-01T00:00:00Z", mrr="7777")
    _upsert_policy(apolice, ticket, {}, ticket_id="T-LOCK-NEW")
    db.session.flush()
    db.session.refresh(locked)

    assert locked.ev_id == ev_old.id
    assert locked.segment == Segment.M
    assert locked.closed_date == date(2025, 1, 1)
    assert locked.mrr_projected == Decimal("7777")
    assert locked.partner_operator == "NewOp"
    assert locked.hubspot_ticket_id == "T-LOCK-NEW"


def test_upsert_resolves_ev_via_owner_map(db_session):
    ev = _ev("from-owner@x")
    owner_map = {"99999": "from-owner@x"}
    apolice = _apolice("A-OWN")
    ticket = _ticket_for_upsert(ev_email="99999")
    _upsert_policy(apolice, ticket, owner_map, ticket_id="T-OWN")
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_apolice_id="A-OWN").one()
    assert policy.ev_id == ev.id
