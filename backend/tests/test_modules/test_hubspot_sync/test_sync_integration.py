"""End-to-end mocked test for run_sync.

Stubs the HubSpotClient at the module level and walks through a realistic
scenario with multiple apolices, tickets in mixed states, and verifies the
final state of `policies` plus the summary counts.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models import Policy, User, UserRole, BenefitType, Client


def _ev(email):
    u = User(email=email, name=email, role=UserRole.EV, active=True)
    db.session.add(u)
    db.session.flush()
    return u


def _apolice(aid, beneficio):
    return {
        "id": aid,
        "properties": {
            "apolice___beneficio": beneficio,
            "numero_apolice": f"AP-{aid}",
            "parceiro": "BradescoTest",
        },
    }


def _ticket_props(ev_email="ev@x", client="ClientCo", mrr="2000",
                  closed="2025-09-01T00:00:00Z", pipeline="651307",
                  stage="11947921"):
    return {
        "solicitante_demanda": ev_email,
        "cliente___nome_da_empresa": client,
        "mrr___receita_mensal": mrr,
        "closed_date": closed,
        "cotar___segmentacao_pipo": "M",
        "hs_pipeline": pipeline,
        "hs_pipeline_stage": stage,
    }


def test_run_sync_end_to_end(db_session):
    _ev("ev@x")

    # Scenario:
    #   A1 (Saúde) → T1 (valid Placement+Gongo+date+default deal) → KEEP
    #   A2 (Odonto) → T1 (same ticket as A1) → KEEP (multiple per ticket)
    #   A3 (Vida) → T2 (wrong pipeline) → SKIP wrong_pipeline
    #   A4 (Saúde e Odonto) → T3 (no default deal associated) → SKIP no_default_deal
    #   A5 (Saúde) → no ticket → SKIP no_ticket
    #   A6 (Saúde) → T4 (closed_date too old) → SKIP too_old

    fake_client = MagicMock()

    # Phase 1: search_deals — apolices
    fake_client.search_deals.return_value = {
        "results": [
            _apolice("A1", "Saúde"),
            _apolice("A2", "Odonto"),
            _apolice("A3", "Vida"),
            _apolice("A4", "Saúde e Odonto"),
            _apolice("A5", "Saúde"),
            _apolice("A6", "Saúde"),
        ],
        "paging": {},
    }

    # Phase 2: batch_read_associations(deals→tickets)
    # Phase 4 also calls batch_read_associations(tickets→deals).
    # We need to differentiate by argument.
    def fake_batch_assoc(from_type, to_type, ids):
        if (from_type, to_type) == ("deals", "tickets"):
            return {
                "A1": ["T1"],
                "A2": ["T1"],
                "A3": ["T2"],
                "A4": ["T3"],
                # A5 absent → no ticket
                "A6": ["T4"],
            }
        if (from_type, to_type) == ("tickets", "deals"):
            return {
                "T1": ["D1"],          # default deal exists
                "T3": ["D-NONDEFAULT"],  # no default deal
                # T4 was filtered out before this phase
            }
        return {}
    fake_client.batch_read_associations.side_effect = fake_batch_assoc

    # Phase 3 + Phase 4: batch_read_objects — tickets first, then deals
    def fake_batch_objects(object_type, ids, properties):
        if object_type == "tickets":
            return {
                "T1": _ticket_props(),
                "T2": _ticket_props(pipeline="999999"),  # wrong pipeline
                "T3": _ticket_props(),
                "T4": _ticket_props(closed="2024-01-01T00:00:00Z"),  # too old
            }
        if object_type == "deals":
            return {
                "D1": {"hs_pipeline": "default"},
                "D-NONDEFAULT": {"hs_pipeline": "999999"},
            }
        return {}
    fake_client.batch_read_objects.side_effect = fake_batch_objects

    fake_client.get_all_owners.return_value = {}

    with patch("app.modules.hubspot_sync.sync.HubSpotClient", return_value=fake_client):
        from app.modules.hubspot_sync.sync import run_sync
        summary = run_sync()

    # Verify summary
    assert summary["created"] == 2  # A1 and A2
    assert summary["updated"] == 0
    assert summary["skipped"]["no_ticket"] == 1     # A5
    assert summary["skipped"]["wrong_pipeline"] == 1  # T2 (filtered → A3 dropped)
    assert summary["skipped"]["too_old"] == 1       # T4 (filtered → A6 dropped)
    assert summary["skipped"]["no_default_deal"] == 1  # T3 → A4 dropped
    assert summary["error_count"] == 0

    # Verify DB state
    rows = Policy.query.order_by(Policy.hubspot_apolice_id).all()
    assert [r.hubspot_apolice_id for r in rows] == ["A1", "A2"]
    a1 = Policy.query.filter_by(hubspot_apolice_id="A1").one()
    a2 = Policy.query.filter_by(hubspot_apolice_id="A2").one()
    assert a1.hubspot_ticket_id == "T1"
    assert a2.hubspot_ticket_id == "T1"
    assert a1.benefit_type == BenefitType.SAUDE
    assert a2.benefit_type == BenefitType.ODONTO
    assert a1.mrr_projected == Decimal("2000")
    assert a2.mrr_projected == Decimal("2000")  # MRR replicated across rows
    assert a1.partner_operator == "BradescoTest"
    assert a1.numero_apolice == "AP-A1"

    # run_sync() calls db.session.commit() internally, which bypasses the
    # rollback-based db_session fixture.  Clean up committed rows explicitly
    # so subsequent tests start with a pristine DB.
    Policy.query.delete()
    Client.query.delete()
    User.query.filter_by(email="ev@x").delete()
    db.session.commit()
