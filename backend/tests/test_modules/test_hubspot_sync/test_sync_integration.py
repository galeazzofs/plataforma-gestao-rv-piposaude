"""End-to-end mocked test for run_sync (ticket-anchored, full-fetch).

Stubs the HubSpotClient at the module level and walks through a realistic
scenario with multiple tickets in mixed states, verifying the final state
of `policies` and the summary counts.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models import Policy, User, UserRole, BenefitType, Client, PlatformSetting
from app.modules.hubspot_sync.sync import (
    APOLICE_PIPELINE_ID,
    DEFAULT_DEAL_PIPELINE_ID,
)


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _ticket(tid, props=None):
    base = {
        "solicitante_demanda": "ev@x",
        "cliente___nome_da_empresa": "ClientCo",
        "mrr___receita_mensal": "2000",
        "closed_date": "2025-09-01T00:00:00Z",
        "cotar___segmentacao_pipo": "M",
        "hs_pipeline": "651307",
        "hs_pipeline_stage": "11947921",
    }
    if props:
        base.update(props)
    return {"id": tid, "properties": base}


def _apolice_props(beneficio, numero="AP-X", parceiro="BradescoTest"):
    return {
        "pipeline": APOLICE_PIPELINE_ID,
        "apolice___beneficio": beneficio,
        "numero_apolice": numero,
        "parceiro": parceiro,
        "hs_v2_date_entered_14038792": "2025-01-15",
    }


def test_run_sync_end_to_end(db_session):
    _ev("ev@x")

    # Scenario:
    #   T1 → D-S (apolice Saúde) + D-O (apolice Odonto) + D-DEFAULT → KEEP both apolices
    #   T2 → D-A2 (apolice Vida) + D-DEFAULT → KEEP
    #   T3 → D-A3 (apolice Saúde e Odonto), no default → SKIP no_default_deal
    #   T4 → D-DEFAULT only → SKIP no_apolice
    fake_client = MagicMock()

    # Phase 1: search_tickets paginates once
    fake_client.search_tickets.return_value = {
        "results": [_ticket("T1"), _ticket("T2"), _ticket("T3"), _ticket("T4")],
        "paging": {},
    }

    # Phase 2a: ticket→deals associations
    fake_client.batch_read_associations.return_value = {
        "T1": ["D-S", "D-O", "D-DEFAULT"],
        "T2": ["D-A2", "D-DEFAULT"],
        "T3": ["D-A3"],
        "T4": ["D-DEFAULT"],
    }
    # Phase 2b: deal property batch_read returns pipeline + apolice props
    fake_client.batch_read_objects.return_value = {
        "D-S": _apolice_props("Saúde", numero="AP-S"),
        "D-O": _apolice_props("Odonto", numero="AP-O"),
        "D-A2": _apolice_props("Vida", numero="AP-V"),
        "D-A3": _apolice_props("Saúde e Odonto", numero="AP-SO"),
        "D-DEFAULT": {"pipeline": DEFAULT_DEAL_PIPELINE_ID},
    }

    fake_client.get_all_owners.return_value = {}

    with patch("app.modules.hubspot_sync.sync.HubSpotClient", return_value=fake_client):
        from app.modules.hubspot_sync.sync import run_sync
        summary = run_sync()

    # Verify summary
    assert summary["created"] == 3  # D-S, D-O (from T1) + D-A2 (from T2)
    assert summary["updated"] == 0
    assert summary["skipped"]["no_default_deal"] == 1  # T3
    assert summary["skipped"]["no_apolice"] == 1       # T4
    assert summary["error_count"] == 0

    # Verify DB state
    rows = Policy.query.order_by(Policy.hubspot_apolice_id).all()
    assert {r.hubspot_apolice_id for r in rows} == {"D-S", "D-O", "D-A2"}
    a_s = Policy.query.filter_by(hubspot_apolice_id="D-S").one()
    a_o = Policy.query.filter_by(hubspot_apolice_id="D-O").one()
    a_v = Policy.query.filter_by(hubspot_apolice_id="D-A2").one()
    assert a_s.benefit_type == BenefitType.SAUDE
    assert a_o.benefit_type == BenefitType.ODONTO
    assert a_v.benefit_type == BenefitType.VIDA
    assert a_s.hubspot_ticket_id == "T1"
    assert a_o.hubspot_ticket_id == "T1"
    assert a_v.hubspot_ticket_id == "T2"
    assert a_s.mrr_projected == Decimal("2000")
    assert a_v.mrr_projected == Decimal("2000")
    assert a_s.numero_apolice == "AP-S"
    assert a_v.partner_operator == "BradescoTest"

    # run_sync() commits internally — clean up explicitly so subsequent tests
    # start with a pristine DB
    Policy.query.delete()
    Client.query.delete()
    User.query.filter_by(email="ev@x").delete()
    PlatformSetting.query.filter(PlatformSetting.key.like("hubspot_last_sync%")).delete()
    db.session.commit()
