"""Tests for the enriched appraisal serializer + recalculate endpoint."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
    FinancialImport, ImportBatch, Commission, EvQuarterAchievement,
    Appraisal, AppraisalStatus, CommissionPctTable,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def review_setup():
    """One admin, one EV, one matched policy + commission + NF for Q3/2026."""
    suffix = uuid.uuid4().hex[:8]

    # Seed pct table for M segment if not present (idempotent on the test DB)
    existing = CommissionPctTable.query.filter_by(version=1, segment="M").first()
    if not existing:
        for seg, mn, mx, pct in [
            ("M", "0.0000", "0.4999", "0.05"),
            ("M", "0.5000", "0.9999", "0.06"),
            ("M", "1.0000", "99.9999", "0.08"),
        ]:
            db.session.add(CommissionPctTable(
                version=1, segment=seg,
                achievement_min=Decimal(mn), achievement_max=Decimal(mx),
                commission_pct=Decimal(pct), valid_from=date.today(),
            ))
        db.session.flush()

    admin = User(email=f"rev-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"rev-ev-{suffix}@x", name="Maria Silva",
              role=UserRole.EV, active=True)
    db.session.add_all([admin, ev])
    db.session.flush()

    client = Client.find_or_create(f"RevClient-{suffix}")
    db.session.flush()

    policy = Policy(
        hubspot_ticket_id=f"REV-T-{suffix}",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2026, 7, 1),  # Q3/2026 gongo
        first_payment_real=date(2026, 7, 15),
    )
    db.session.add(policy)
    db.session.flush()

    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=3, year=2026,
        achievement_pct=Decimal("0.75"),
    ))
    db.session.flush()

    appraisal = Appraisal(
        quarter=3, year=2026, status=AppraisalStatus.CALCULATING,
        created_by=admin.id,
    )
    db.session.add(appraisal)
    db.session.flush()

    batch = ImportBatch(filename="rev.xlsx", uploaded_by=admin.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()

    nf = FinancialImport(
        import_batch_id=batch.id, quarter=3, year=2026,
        nf_valor_liquido=Decimal("1000.00"),
        nf_mes_recebimento="2026-08",
        cliente_mae=client.name,
        operadora="SulAmerica",
        produto="Saúde",
        tipo_receita="Comissão",
        status_recebimento="RECEBIDO",
        data_recebimento=date(2026, 8, 10),
        match_status="UNMATCHED",
    )
    db.session.add(nf)
    db.session.flush()
    db.session.commit()

    yield admin, ev, client, policy, appraisal, nf

    # Teardown
    Commission.query.filter_by(quarter=3, year=2026).delete()
    FinancialImport.query.filter_by(quarter=3, year=2026).delete()
    EvQuarterAchievement.query.filter_by(ev_id=ev.id).delete()
    db.session.delete(batch)
    db.session.delete(appraisal)
    Policy.query.filter_by(id=policy.id).delete()
    db.session.delete(client)
    db.session.delete(admin)
    db.session.delete(ev)
    # Clean up the seeded pct table so other tests can re-seed
    CommissionPctTable.query.filter_by(version=1).delete()
    db.session.commit()


def test_recalculate_runs_calculator_and_returns_detail(client, review_setup):
    admin, ev, client_obj, policy, appraisal, nf = review_setup

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/recalculate",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]

    assert body["status"] == "CALCULATING"
    assert "ev_summary" in body
    assert "totals" in body
    assert body["totals"]["matched_nf_count"] == 1

    # The single EV's policy + commission should appear in ev_summary
    assert len(body["ev_summary"]) == 1
    ev_block = body["ev_summary"][0]
    assert ev_block["ev_name"] == "Maria Silva"
    assert ev_block["policies_count"] == 1
    assert ev_block["total_commission"] == 60.0  # 1000 * 0.06
    assert len(ev_block["policies"]) == 1
    assert ev_block["policies"][0]["nfs"][0]["nf_liquido"] == 1000.0


def test_recalculate_blocked_when_locked(client, review_setup):
    admin, _, _, _, appraisal, _ = review_setup
    appraisal.status = AppraisalStatus.LOCKED
    db.session.commit()

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/recalculate",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"]["code"] == "CONFLICT"


def test_get_appraisal_detail_includes_drill_down(client, review_setup):
    admin, _, _, _, appraisal, _ = review_setup

    # First trigger a recalc to populate commissions
    client.post(
        f"/api/v1/appraisals/{appraisal.id}/recalculate",
        headers=_auth_header(admin),
    )

    resp = client.get(
        f"/api/v1/appraisals/{appraisal.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert "ev_summary" in body
    assert "unmatched" in body
    assert "expired" in body
    assert "nao_suportado" in body
    assert body["totals"]["matched_nf_count"] == 1
