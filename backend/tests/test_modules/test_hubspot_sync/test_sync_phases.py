"""Tests for individual phases of the ticket-anchored sync (1 row per ticket)."""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.modules.hubspot_sync.sync import (
    _fetch_tickets,
    _resolve_ticket_deals,
    _new_summary,
    APOLICE_PIPELINE_ID,
    PLACEMENT_PIPELINE_ID,
    GONGO_STAGE_ID,
    GONGO_DATE_FLOOR,
    DEFAULT_DEAL_PIPELINE_ID,
    VALID_BENEFITS_HUBSPOT,
    TIME_SOLICITANTE_VENDAS,
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
    # 4 filters AND-ed: pipeline, stage, closed_date floor, time_solicitante=Vendas
    assert len(filters) == 4
    pipeline_f = next(f for f in filters if f["propertyName"] == "hs_pipeline")
    assert pipeline_f["operator"] == "EQ"
    assert pipeline_f["value"] == PLACEMENT_PIPELINE_ID

    stage_f = next(f for f in filters if f["propertyName"] == "hs_pipeline_stage")
    assert stage_f["operator"] == "EQ"
    assert stage_f["value"] == GONGO_STAGE_ID

    date_f = next(f for f in filters if f["propertyName"] == "closed_date")
    assert date_f["operator"] == "GTE"
    assert date_f["value"] == GONGO_DATE_FLOOR.isoformat()

    time_f = next(f for f in filters if f["propertyName"] == "time_solicitante")
    assert time_f["operator"] == "EQ"
    assert time_f["value"] == TIME_SOLICITANTE_VENDAS

    assert set(call_kwargs["properties"]) == set(TICKET_PROPERTIES)


def test_fetch_tickets_no_longer_accepts_since_argument():
    """_fetch_tickets is full-fetch always — no incremental cursor."""
    import inspect
    sig = inspect.signature(_fetch_tickets)
    assert list(sig.parameters) == ["client"]


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


# --- _resolve_ticket_deals ---

def _ticket(tid):
    return {"id": tid, "properties": {}}


def _apolice_props(beneficio="Saúde", numero="AP-001", parceiro="Bradesco",
                   entered="2025-01-15"):
    return {
        "pipeline": APOLICE_PIPELINE_ID,
        "apolice___beneficio": beneficio,
        "numero_apolice": numero,
        "parceiro": parceiro,
        "hs_v2_date_entered_14038792": entered,
    }


def _default_deal_props(closedate="2025-06-01T00:00:00Z"):
    return {"pipeline": DEFAULT_DEAL_PIPELINE_ID, "closedate": closedate}


def test_resolve_keeps_ticket_with_apolice_in_pre_ativacao_and_default():
    client = MagicMock()
    client.batch_read_associations.return_value = {"T1": ["D-A", "D-DEFAULT"]}
    client.batch_read_objects.return_value = {
        "D-A": _apolice_props(beneficio="Saúde", numero="AP-001", parceiro="Bradesco"),
        "D-DEFAULT": _default_deal_props(),
    }
    summary = _new_summary()

    result = _resolve_ticket_deals(client, [_ticket("T1")], summary)

    assert "T1" in result
    assert result["T1"]["apolice"]["id"] == "D-A"
    assert result["T1"]["apolice"]["properties"]["numero_apolice"] == "AP-001"
    assert result["T1"]["default_deal"]["id"] == "D-DEFAULT"
    assert result["T1"]["default_deal"]["properties"]["closedate"] == "2025-06-01T00:00:00Z"

    deal_call = client.batch_read_objects.call_args
    assert deal_call.args[0] == "deals"
    assert set(deal_call.args[2]) == set(DEAL_PROPERTIES)


def test_resolve_drops_apolice_without_pre_ativacao_date():
    """Apolice with no hs_v2_date_entered_14038792 doesn't count — ticket skipped."""
    client = MagicMock()
    client.batch_read_associations.return_value = {"T1": ["D-A", "D-DEFAULT"]}
    client.batch_read_objects.return_value = {
        "D-A": {
            "pipeline": APOLICE_PIPELINE_ID,
            "apolice___beneficio": "Saúde",
            "numero_apolice": "AP-001",
            "parceiro": "Bradesco",
            # hs_v2_date_entered_14038792 missing
        },
        "D-DEFAULT": _default_deal_props(),
    }
    summary = _new_summary()

    result = _resolve_ticket_deals(client, [_ticket("T1")], summary)

    assert result == {}
    assert summary["skipped"]["no_apolice_pre_ativacao"] == 1


def test_resolve_drops_apolice_with_pre_ativacao_before_floor():
    client = MagicMock()
    client.batch_read_associations.return_value = {"T1": ["D-A", "D-DEFAULT"]}
    client.batch_read_objects.return_value = {
        "D-A": _apolice_props(entered="2024-08-15"),
        "D-DEFAULT": _default_deal_props(),
    }
    summary = _new_summary()

    result = _resolve_ticket_deals(client, [_ticket("T1")], summary)

    assert result == {}
    assert summary["skipped"]["no_apolice_pre_ativacao"] == 1


def test_resolve_drops_apolice_with_invalid_benefit():
    client = MagicMock()
    client.batch_read_associations.return_value = {"T1": ["D-A", "D-DEFAULT"]}
    client.batch_read_objects.return_value = {
        "D-A": _apolice_props(beneficio="Outro"),
        "D-DEFAULT": _default_deal_props(),
    }
    summary = _new_summary()

    result = _resolve_ticket_deals(client, [_ticket("T1")], summary)

    assert result == {}
    assert summary["skipped"]["no_apolice_pre_ativacao"] == 1


def test_resolve_drops_ticket_without_default_deal():
    client = MagicMock()
    client.batch_read_associations.return_value = {"T1": ["D-A"]}
    client.batch_read_objects.return_value = {
        "D-A": _apolice_props(),
    }
    summary = _new_summary()

    result = _resolve_ticket_deals(client, [_ticket("T1")], summary)

    assert result == {}
    assert summary["skipped"]["no_default_deal"] == 1


def test_resolve_drops_ticket_with_no_associated_deals():
    client = MagicMock()
    client.batch_read_associations.return_value = {}
    client.batch_read_objects.return_value = {}
    summary = _new_summary()

    result = _resolve_ticket_deals(client, [_ticket("T1")], summary)

    assert result == {}
    # No apolice in pré-ativação means no_apolice_pre_ativacao kicks first
    assert summary["skipped"]["no_apolice_pre_ativacao"] == 1


def test_resolve_warns_and_picks_first_when_multiple_apolices_in_pre_ativacao():
    """User says this never happens in practice. If it does, we still proceed
    with the first one and log it via summary["skipped"]["multiple_apolices"]."""
    client = MagicMock()
    client.batch_read_associations.return_value = {"T1": ["D-A1", "D-A2", "D-DEFAULT"]}
    client.batch_read_objects.return_value = {
        "D-A1": _apolice_props(numero="AP-001"),
        "D-A2": _apolice_props(numero="AP-002"),
        "D-DEFAULT": _default_deal_props(),
    }
    summary = _new_summary()

    result = _resolve_ticket_deals(client, [_ticket("T1")], summary)

    assert "T1" in result
    assert result["T1"]["apolice"]["id"] == "D-A1"  # first one
    assert summary["skipped"]["multiple_apolices"] == 1


def test_resolve_empty_input():
    client = MagicMock()
    summary = _new_summary()

    result = _resolve_ticket_deals(client, [], summary)

    assert result == {}
    client.batch_read_associations.assert_not_called()
    client.batch_read_objects.assert_not_called()


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


def _default_deal(deal_id="D-DEFAULT", closedate="2025-06-01T00:00:00Z"):
    return {"id": deal_id, "properties": {"closedate": closedate}}


def _ticket_for_upsert(ev_email="ev@x", client_name="ClientCo", mrr="1500",
                      segment="M"):
    return {
        "solicitante_demanda": ev_email,
        "cliente___nome_da_empresa": client_name,
        "mrr___receita_mensal": mrr,
        "cotar___segmentacao_pipo": segment,
        "hs_pipeline": "651307",
        "hs_pipeline_stage": "11947921",
        "time_solicitante": "Vendas",
    }


def test_upsert_creates_new_policy(db_session):
    ev = _ev("ev@x")
    apolice = _apolice("A1", beneficio="Saúde", numero="AP-001", parceiro="Bradesco")
    deal = _default_deal(closedate="2025-06-01T00:00:00Z")
    ticket = _ticket_for_upsert(ev_email="ev@x", client_name="Acme", mrr="2500")

    is_new = _upsert_policy("T1", ticket, apolice, deal, {})
    db.session.flush()

    assert is_new is True
    policy = Policy.query.filter_by(hubspot_ticket_id="T1").one()
    assert policy.hubspot_apolice_id == "A1"
    assert policy.numero_apolice == "AP-001"
    assert policy.partner_operator == "Bradesco"
    assert policy.benefit_type == BenefitType.SAUDE
    assert policy.mrr_projected == Decimal("2500")
    assert policy.ev_id == ev.id
    assert policy.client.name == Client.find_or_create("Acme").name
    assert policy.segment == Segment.M
    assert policy.closed_date == date(2025, 6, 1)


def test_upsert_closed_date_comes_from_default_deal_not_ticket(db_session):
    """closed_date sourced from default deal's `closedate`, not ticket's `closed_date`."""
    _ev("ev-cd@x")
    apolice = _apolice("A-CD")
    deal = _default_deal(closedate="2025-12-31T00:00:00Z")
    ticket = _ticket_for_upsert(ev_email="ev-cd@x")
    # Ticket's own closed_date is irrelevant — should be ignored
    ticket["closed_date"] = "1999-01-01T00:00:00Z"

    _upsert_policy("T-CD", ticket, apolice, deal, {})
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_ticket_id="T-CD").one()
    assert policy.closed_date == date(2025, 12, 31)


def test_upsert_updates_existing_policy_by_ticket_id(db_session):
    ev = _ev("ev2@x")
    existing = Policy(
        hubspot_apolice_id="A-OLD",
        hubspot_ticket_id="T2",
        ev_id=ev.id,
        mrr_projected=Decimal("100"),
    )
    db.session.add(existing)
    db.session.flush()

    apolice = _apolice("A-NEW", numero="AP-NEW")
    deal = _default_deal()
    ticket = _ticket_for_upsert(ev_email="ev2@x", mrr="9999")

    is_new = _upsert_policy("T2", ticket, apolice, deal, {})
    db.session.flush()

    assert is_new is False
    db.session.refresh(existing)
    assert existing.mrr_projected == Decimal("9999")
    assert existing.numero_apolice == "AP-NEW"
    assert existing.hubspot_apolice_id == "A-NEW"  # apolice_id is non-unique now and is overwritten


def test_upsert_saude_e_odonto_maps_to_combined_enum(db_session):
    _ev("ev3@x")
    apolice = _apolice("A3", beneficio="Saúde e Odonto")
    deal = _default_deal()
    ticket = _ticket_for_upsert(ev_email="ev3@x")
    _upsert_policy("T3", ticket, apolice, deal, {})
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_ticket_id="T3").one()
    assert policy.benefit_type == BenefitType.SAUDE_ODONTO


def test_upsert_idempotent_when_called_twice_for_same_ticket(db_session):
    _ev("ev4@x")
    apolice = _apolice("A4")
    deal = _default_deal()
    ticket = _ticket_for_upsert(ev_email="ev4@x", mrr="3000")

    _upsert_policy("T4", ticket, apolice, deal, {})
    _upsert_policy("T4", ticket, apolice, deal, {})
    db.session.flush()

    rows = Policy.query.filter_by(hubspot_ticket_id="T4").all()
    assert len(rows) == 1


def test_upsert_respects_is_locked_for_lockable_fields(db_session):
    ev_old = _ev("locked-old@x")
    _ev("locked-new@x")
    locked = Policy(
        hubspot_apolice_id="A-LOCK-OLD",
        hubspot_ticket_id="T-LOCK",
        ev_id=ev_old.id,
        segment=Segment.M,
        closed_date=date(2025, 1, 1),
        is_locked=True,
    )
    db.session.add(locked)
    db.session.flush()

    apolice = _apolice("A-LOCK-NEW", parceiro="NewOp")
    deal = _default_deal(closedate="2026-03-01T00:00:00Z")
    ticket = _ticket_for_upsert(ev_email="locked-new@x", segment="G", mrr="7777")
    _upsert_policy("T-LOCK", ticket, apolice, deal, {})
    db.session.flush()
    db.session.refresh(locked)

    # Lockable preserved
    assert locked.ev_id == ev_old.id
    assert locked.segment == Segment.M
    assert locked.closed_date == date(2025, 1, 1)
    # Non-lockable updated (incl. apolice id pointer)
    assert locked.mrr_projected == Decimal("7777")
    assert locked.partner_operator == "NewOp"
    assert locked.hubspot_apolice_id == "A-LOCK-NEW"


def test_upsert_resolves_ev_via_owner_map(db_session):
    ev = _ev("from-owner@x")
    owner_map = {"99999": "from-owner@x"}
    apolice = _apolice("A-OWN")
    deal = _default_deal()
    ticket = _ticket_for_upsert(ev_email="99999")
    _upsert_policy("T-OWN", ticket, apolice, deal, owner_map)
    db.session.flush()
    policy = Policy.query.filter_by(hubspot_ticket_id="T-OWN").one()
    assert policy.ev_id == ev.id


# --- _delete_absent_policies ---

from app.models import Commission, EvValidation, FinancialImport, Appraisal
from app.models.appraisal import AppraisalStatus
from app.models.ev_validation import ValidationStatus
from app.models.financial_import import ImportBatch
from app.modules.hubspot_sync.sync import _delete_absent_policies


def _make_policy(ticket_id, ev_id, locked=False):
    p = Policy(
        hubspot_ticket_id=ticket_id,
        hubspot_apolice_id=f"A-{ticket_id}",
        ev_id=ev_id,
        is_locked=locked,
    )
    db.session.add(p)
    db.session.flush()
    return p


def test_delete_absent_policies_removes_policies_not_in_fetch(db_session):
    ev = _ev("delete-test@x")
    _make_policy("KEEP-1", ev.id)
    _make_policy("DROP-1", ev.id)

    summary = _new_summary()
    _delete_absent_policies({"KEEP-1"}, summary)
    db.session.flush()

    assert Policy.query.filter_by(hubspot_ticket_id="KEEP-1").one()
    assert Policy.query.filter_by(hubspot_ticket_id="DROP-1").first() is None
    assert summary["deleted"] == 1


def test_delete_absent_policies_no_op_when_all_seen(db_session):
    ev = _ev("delete-noop@x")
    _make_policy("A1", ev.id)
    _make_policy("A2", ev.id)

    summary = _new_summary()
    _delete_absent_policies({"A1", "A2"}, summary)
    db.session.flush()

    assert Policy.query.count() == 2
    assert summary["deleted"] == 0


def test_delete_absent_policies_cascades_commissions(db_session):
    ev = _ev("delete-cascade-c@x")
    p_keep = _make_policy("CASC-KEEP", ev.id)
    p_drop = _make_policy("CASC-C", ev.id)
    c_keep = Commission(policy_id=p_keep.id, ev_id=ev.id, quarter=1, year=2025)
    c_drop = Commission(policy_id=p_drop.id, ev_id=ev.id, quarter=1, year=2025)
    db.session.add_all([c_keep, c_drop])
    db.session.flush()
    c_drop_id = c_drop.id

    summary = _new_summary()
    _delete_absent_policies({"CASC-KEEP"}, summary)
    db.session.flush()

    assert Commission.query.filter_by(id=c_drop_id).first() is None
    assert Commission.query.filter_by(policy_id=p_keep.id).count() == 1
    assert summary["deleted"] == 1


def test_delete_absent_policies_cascades_ev_validations(db_session):
    import random
    ev = _ev("delete-cascade-v@x")
    p_keep = _make_policy("CASC-V-KEEP", ev.id)
    p_drop = _make_policy("CASC-V-DROP", ev.id)
    appraisal = Appraisal(
        quarter=1,
        year=2099 + random.randint(0, 99999),
        status=AppraisalStatus.DRAFT,
        created_by=ev.id,
    )
    db.session.add(appraisal)
    db.session.flush()
    v_drop = EvValidation(
        appraisal_id=appraisal.id,
        policy_id=p_drop.id,
        ev_id=ev.id,
        status=ValidationStatus.PENDING,
    )
    db.session.add(v_drop)
    db.session.flush()
    v_drop_id = v_drop.id

    summary = _new_summary()
    _delete_absent_policies({"CASC-V-KEEP"}, summary)
    db.session.flush()

    assert EvValidation.query.filter_by(id=v_drop_id).first() is None


def test_delete_absent_policies_nulls_financial_imports(db_session):
    ev = _ev("delete-fi@x")
    p_keep = _make_policy("FI-KEEP", ev.id)
    p_drop = _make_policy("FI-DROP", ev.id)
    batch = ImportBatch(filename="test.csv", uploaded_by=ev.id)
    db.session.add(batch)
    db.session.flush()
    fi = FinancialImport(
        import_batch_id=batch.id,
        policy_id=p_drop.id,
        numero_apolice="X",
        nf_valor_liquido=Decimal("100.00"),
        nf_mes_recebimento="2025-01",
        quarter=1,
        year=2025,
    )
    db.session.add(fi)
    db.session.flush()
    fi_id = fi.id

    summary = _new_summary()
    _delete_absent_policies({"FI-KEEP"}, summary)
    db.session.flush()
    # Bulk update used synchronize_session=False — expire identity map so the
    # re-query sees the new policy_id=None instead of the cached value.
    db.session.expire_all()

    fi_after = FinancialImport.query.filter_by(id=fi_id).one()
    assert fi_after.policy_id is None  # unlinked, not deleted


def test_delete_absent_policies_deletes_locked_rows(db_session):
    ev = _ev("delete-locked@x")
    _make_policy("LOCK-DROP", ev.id, locked=True)

    summary = _new_summary()
    _delete_absent_policies({"OTHER"}, summary)
    db.session.flush()

    assert Policy.query.filter_by(hubspot_ticket_id="LOCK-DROP").first() is None
    assert summary["deleted"] == 1


def test_delete_absent_policies_aborts_when_seen_empty_but_db_nonempty(db_session):
    ev = _ev("delete-guard@x")
    _make_policy("GUARD-1", ev.id)
    _make_policy("GUARD-2", ev.id)

    summary = _new_summary()
    _delete_absent_policies(set(), summary)
    db.session.flush()

    assert Policy.query.count() == 2
    assert summary["deleted"] == 0
    assert any("Delete-by-absence" in e for e in summary["errors"])
    assert summary["error_count"] >= 1


def test_delete_absent_policies_empty_db_empty_seen_is_safe(db_session):
    summary = _new_summary()
    _delete_absent_policies(set(), summary)
    assert summary["deleted"] == 0
    assert summary["errors"] == []
