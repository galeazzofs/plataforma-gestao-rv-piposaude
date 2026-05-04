"""End-to-end mocked test for run_sync (ticket-anchored, full-fetch, 1 row per ticket).

Stubs the HubSpotClient at the module level and walks through a realistic
scenario with multiple tickets in mixed states, verifying the final state
of `policies`, the summary counts, and the delete-by-absence behaviour.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models import Policy, User, UserRole, BenefitType, Client, PlatformSetting
from app.modules.hubspot_sync.sync import (
    APOLICE_PIPELINE_ID,
    PRE_ATIVACAO_STAGE_ID,
    DEFAULT_DEAL_PIPELINE_ID,
    GANHO_STAGE_ID,
)


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _ticket(tid, props=None, beneficio="Saúde"):
    base = {
        "solicitante_demanda": "ev@x",
        "cliente___nome_da_empresa": "ClientCo",
        "mrr___receita_mensal": "2000",
        "closed_date": "2025-09-01T00:00:00Z",
        "cotar___segmentacao_pipo": "M",
        "beneficio_a_ser_cotado": beneficio,
        "hs_pipeline": "651307",
        "hs_pipeline_stage": "11947921",
    }
    if props:
        base.update(props)
    return {"id": tid, "properties": base}


def _apolice_props(numero="AP-X", parceiro="BradescoTest",
                   entered="2025-01-15", stage=PRE_ATIVACAO_STAGE_ID):
    """Apólice deal payload — benefit lives on the ticket now."""
    return {
        "pipeline": APOLICE_PIPELINE_ID,
        "dealstage": stage,
        "numero_apolice": numero,
        "parceiro": parceiro,
        "hs_v2_date_entered_14038792": entered,
    }


def _default_deal_props(closedate="2025-06-01T00:00:00Z", stage=GANHO_STAGE_ID):
    return {
        "pipeline": DEFAULT_DEAL_PIPELINE_ID,
        "dealstage": stage,
        "closedate": closedate,
    }


def _cleanup(emails):
    Policy.query.delete()
    Client.query.delete()
    for e in emails:
        User.query.filter_by(email=e).delete()
    PlatformSetting.query.filter(PlatformSetting.key.like("hubspot_last_sync%")).delete()
    db.session.commit()


def test_run_sync_end_to_end(db_session):
    _ev("ev@x")

    # Scenario:
    #   T1 → D-A1 (apolice Saúde, pré-ativação) + D-DEFAULT (Ganho) → KEEP (1 row)
    #   T2 → D-A2 (apolice Vida, pré-ativação) + D-DEFAULT (Ganho) → KEEP (1 row)
    #   T3 → D-A3 (apolice no pré-ativação) + D-DEFAULT (Ganho) → SKIP no_apolice_pre_ativacao
    #   T4 → D-DEFAULT only → SKIP no_apolice_pre_ativacao
    #   T5 → D-A5 (apolice em pré-ativação) only → SKIP no_default_deal
    #   T6 → benefit inválido → SKIP invalid_benefit
    #   T7 → D-A7 (apolice ok) + D-DEFAULT-EARLY (stage qualifiedtobuy) → SKIP no_default_deal
    fake_client = MagicMock()
    fake_client.search_tickets.return_value = {
        "results": [
            _ticket("T1", beneficio="Saúde"),
            _ticket("T2", beneficio="Vida"),
            _ticket("T3", beneficio="Saúde"),
            _ticket("T4", beneficio="Saúde"),
            _ticket("T5", beneficio="Saúde"),
            _ticket("T6", beneficio="Outro"),  # invalid benefit on the ticket
            _ticket("T7", beneficio="Saúde"),
        ],
        "paging": {},
    }
    fake_client.batch_read_associations.return_value = {
        "T1": ["D-A1", "D-DEFAULT"],
        "T2": ["D-A2", "D-DEFAULT"],
        "T3": ["D-A3", "D-DEFAULT"],
        "T4": ["D-DEFAULT"],
        "T5": ["D-A5"],
        "T6": ["D-A6", "D-DEFAULT"],
        "T7": ["D-A7", "D-DEFAULT-EARLY"],
    }
    fake_client.batch_read_objects.return_value = {
        "D-A1": _apolice_props(numero="AP-1"),
        "D-A2": _apolice_props(numero="AP-2"),
        "D-A3": _apolice_props(numero="AP-3", entered=None),
        "D-A5": _apolice_props(numero="AP-5"),
        "D-A6": _apolice_props(numero="AP-6"),
        "D-A7": _apolice_props(numero="AP-7"),
        "D-DEFAULT": _default_deal_props(closedate="2025-09-01T00:00:00Z"),
        "D-DEFAULT-EARLY": _default_deal_props(stage="qualifiedtobuy"),
    }
    fake_client.get_all_owners.return_value = {}

    with patch("app.modules.hubspot_sync.sync.HubSpotClient", return_value=fake_client):
        from app.modules.hubspot_sync.sync import run_sync
        summary = run_sync()

    assert summary["created"] == 2  # T1, T2
    assert summary["updated"] == 0
    assert summary["deleted"] == 0  # nothing pre-existing to delete
    assert summary["skipped"]["invalid_benefit"] == 1          # T6
    assert summary["skipped"]["no_apolice_pre_ativacao"] == 2  # T3, T4
    assert summary["skipped"]["no_default_deal"] == 2          # T5, T7
    assert summary["error_count"] == 0

    rows = Policy.query.order_by(Policy.hubspot_ticket_id).all()
    assert {r.hubspot_ticket_id for r in rows} == {"T1", "T2"}
    p_t1 = Policy.query.filter_by(hubspot_ticket_id="T1").one()
    p_t2 = Policy.query.filter_by(hubspot_ticket_id="T2").one()
    # benefit comes from the ticket, not the apólice
    assert p_t1.benefit_type == BenefitType.SAUDE
    assert p_t2.benefit_type == BenefitType.VIDA
    assert p_t1.hubspot_apolice_id == "D-A1"
    assert p_t2.hubspot_apolice_id == "D-A2"
    assert p_t1.numero_apolice == "AP-1"
    assert p_t1.partner_operator == "BradescoTest"
    assert p_t1.mrr_projected == Decimal("2000")

    _cleanup(["ev@x"])


def test_run_sync_deletes_policies_not_in_fetch(db_session):
    """Pre-existing policy whose ticket id no longer appears is deleted."""
    ev = _ev("ev-del@x")

    stale = Policy(
        hubspot_ticket_id="STALE-T1",
        hubspot_apolice_id="STALE-A1",
        ev_id=ev.id,
    )
    db.session.add(stale)
    db.session.flush()

    fake_client = MagicMock()
    fake_client.search_tickets.return_value = {
        "results": [_ticket("T-FRESH", {"solicitante_demanda": "ev-del@x"})],
        "paging": {},
    }
    fake_client.batch_read_associations.return_value = {
        "T-FRESH": ["D-FRESH", "D-DEFAULT"],
    }
    fake_client.batch_read_objects.return_value = {
        "D-FRESH": _apolice_props(numero="AP-FRESH"),
        "D-DEFAULT": _default_deal_props(),
    }
    fake_client.get_all_owners.return_value = {}

    with patch("app.modules.hubspot_sync.sync.HubSpotClient", return_value=fake_client):
        from app.modules.hubspot_sync.sync import run_sync
        summary = run_sync()

    assert summary["created"] == 1
    assert summary["deleted"] == 1
    assert Policy.query.filter_by(hubspot_ticket_id="STALE-T1").first() is None
    assert Policy.query.filter_by(hubspot_ticket_id="T-FRESH").one()

    _cleanup(["ev-del@x"])


def test_run_sync_does_not_delete_when_errors_occur(db_session):
    """Sync with upsert errors must NOT trigger delete-by-absence."""
    ev = _ev("ev-err@x")
    stale = Policy(
        hubspot_ticket_id="STALE-T2",
        hubspot_apolice_id="STALE-A2",
        ev_id=ev.id,
    )
    db.session.add(stale)
    # Commit so the per-ticket rollback inside run_sync doesn't undo the seed.
    db.session.commit()

    fake_client = MagicMock()
    fake_client.search_tickets.return_value = {
        "results": [_ticket("T-ERR", {"solicitante_demanda": "ev-err@x"})],
        "paging": {},
    }
    fake_client.batch_read_associations.return_value = {
        "T-ERR": ["D-A", "D-DEFAULT"],
    }
    fake_client.batch_read_objects.return_value = {
        "D-A": _apolice_props(),
        "D-DEFAULT": _default_deal_props(),
    }
    fake_client.get_all_owners.return_value = {}

    with patch("app.modules.hubspot_sync.sync.HubSpotClient", return_value=fake_client), \
         patch("app.modules.hubspot_sync.sync._upsert_policy", side_effect=RuntimeError("boom")):
        from app.modules.hubspot_sync.sync import run_sync
        summary = run_sync()

    assert summary["error_count"] >= 1
    assert summary["deleted"] == 0
    assert Policy.query.filter_by(hubspot_ticket_id="STALE-T2").one()  # preserved

    _cleanup(["ev-err@x"])
