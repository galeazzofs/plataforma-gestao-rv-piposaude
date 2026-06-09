"""Tests for the EV validation endpoints.

Covers the 409-on-double-submit fix (approve is now idempotent) and the
enriched per-apólice serializer the EV drills into from the validation row.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
    FinancialImport, ImportBatch, Commission,
    Appraisal, AppraisalStatus, EvValidation, ValidationStatus, AuditLog,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def validation_setup():
    """An admin + EV with one PENDING validation backed by a commission and a
    matched NF for the 08/2026 apuração."""
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"val-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"val-ev-{suffix}@x", name="Joao EV",
              role=UserRole.EV, active=True)
    db.session.add_all([admin, ev])
    db.session.flush()

    client_obj = Client.find_or_create(f"ValClient-{suffix}")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id=f"A-VAL-{suffix}",
        hubspot_ticket_id=f"VAL-T-{suffix}",
        numero_apolice=f"AP-VAL-{suffix}",
        ev_id=ev.id, client_id=client_obj.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2026, 7, 1),
        first_payment_real=date(2026, 7, 15),
        installments_paid=3,
    )
    db.session.add(policy)
    db.session.flush()

    appraisal = Appraisal(
        month=8, year=2026, status=AppraisalStatus.VALIDATING,
        created_by=admin.id,
    )
    db.session.add(appraisal)
    db.session.flush()

    batch = ImportBatch(filename="val.xlsx", uploaded_by=admin.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()

    nf = FinancialImport(
        import_batch_id=batch.id, month=8, year=2026,
        nf_valor_liquido=Decimal("1000.00"),
        nf_mes_recebimento="2026-08",
        cliente_mae=client_obj.name,
        operadora="SulAmerica",
        produto="Saude",
        numero_apolice=policy.numero_apolice,
        tipo_receita="Comissao",
        status_recebimento="RECEBIDO",
        data_recebimento=date(2026, 8, 10),
        match_status="MATCHED",
        policy_id=policy.id,
    )
    db.session.add(nf)

    commission = Commission(
        policy_id=policy.id, ev_id=ev.id, month=8, year=2026,
        segment="M",
        achievement_pct=Decimal("0.75"),
        commission_pct=Decimal("0.06"),
        monthly_actual=Decimal("60.00"),
        total_actual=Decimal("60.00"),
    )
    db.session.add(commission)

    validation = EvValidation(
        appraisal_id=appraisal.id, policy_id=policy.id, ev_id=ev.id,
        status=ValidationStatus.PENDING,
    )
    db.session.add(validation)
    db.session.commit()

    yield {
        "admin": admin, "ev": ev, "policy": policy, "appraisal": appraisal,
        "validation": validation,
    }

    # Teardown — children before parents; clear audit_log to free user FKs.
    EvValidation.query.filter_by(appraisal_id=appraisal.id).delete()
    Commission.query.filter_by(month=8, year=2026).delete()
    FinancialImport.query.filter_by(month=8, year=2026).delete()
    AuditLog.query.filter(
        AuditLog.user_id.in_([admin.id, ev.id])
    ).delete(synchronize_session=False)
    db.session.delete(batch)
    db.session.delete(appraisal)
    Policy.query.filter_by(id=policy.id).delete()
    db.session.delete(client_obj)
    db.session.delete(admin)
    db.session.delete(ev)
    db.session.commit()


def test_approve_pending_then_reapprove_is_idempotent(client, validation_setup):
    """The original 409 bug: a double-click re-POSTed an already-approved row.
    Approve now no-ops on the second call and returns 200, not 409."""
    ev = validation_setup["ev"]
    vid = validation_setup["validation"].id

    first = client.post(f"/api/v1/validations/{vid}/approve",
                        headers=_auth_header(ev))
    assert first.status_code == 200
    assert first.get_json()["data"]["status"] == "APPROVED"

    second = client.post(f"/api/v1/validations/{vid}/approve",
                         headers=_auth_header(ev))
    assert second.status_code == 200, second.get_json()
    assert second.get_json()["data"]["status"] == "APPROVED"


def test_reapprove_redrives_stalled_appraisal_advance(client, validation_setup):
    """The no-op approve path must still re-run the (idempotent) advance hook,
    so a re-approve can recover an appraisal left stuck in VALIDATING after a
    failed/rolled-back hook on the first approve."""
    ev = validation_setup["ev"]
    appraisal = validation_setup["appraisal"]
    vid = validation_setup["validation"].id

    # First approve of the sole validation advances it out of VALIDATING.
    first = client.post(f"/api/v1/validations/{vid}/approve",
                        headers=_auth_header(ev))
    assert first.status_code == 200
    db.session.refresh(appraisal)
    assert appraisal.status == AppraisalStatus.REVOPS_REVIEW

    # Simulate a stalled advance — shove it back to VALIDATING.
    appraisal.status = AppraisalStatus.VALIDATING
    db.session.commit()

    # A re-approve hits the no-op branch but must re-drive the advance.
    second = client.post(f"/api/v1/validations/{vid}/approve",
                         headers=_auth_header(ev))
    assert second.status_code == 200
    db.session.refresh(appraisal)
    assert appraisal.status == AppraisalStatus.REVOPS_REVIEW


def test_approve_contested_validation_conflicts(client, validation_setup):
    """A genuine state conflict still 409s: approving a row the EV already
    contested would silently bury the objection."""
    ev = validation_setup["ev"]
    vid = validation_setup["validation"].id

    contest = client.post(f"/api/v1/validations/{vid}/contest",
                          json={"comment": "MRR errado"},
                          headers=_auth_header(ev))
    assert contest.status_code == 200
    assert contest.get_json()["data"]["status"] == "CONTESTED"

    resp = client.post(f"/api/v1/validations/{vid}/approve",
                       headers=_auth_header(ev))
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CONFLICT"


def test_validation_list_includes_apolice_detail(client, validation_setup):
    """The serializer carries the per-apólice drill-in: operadora, the 12-month
    clock, achievement / commission %, NF total and the NF breakdown."""
    ev = validation_setup["ev"]

    resp = client.get("/api/v1/validations", headers=_auth_header(ev))
    assert resp.status_code == 200
    rows = resp.get_json()["data"]
    assert len(rows) == 1
    row = rows[0]

    assert row["operadora"] == "SulAmerica"
    assert row["segment"] == "M"
    assert row["installments_paid"] == 3
    assert row["achievement_pct"] == 75.0
    assert row["commission_monthly"] == "60.00"
    assert row["nf_liquido_total"] == 1000.0

    assert len(row["nfs"]) == 1
    assert row["nfs"][0]["nf_liquido"] == 1000.0
    assert row["nfs"][0]["tipo_receita"] == "Comissao"
