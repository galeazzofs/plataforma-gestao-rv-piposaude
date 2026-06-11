"""Engine state guards (#60).

CONTEXT.md:123 — an A-apurar month "does not officially update paid months
until LOCKED". The calculator used to persist installments_paid increments
and promote SETTLED during the committed run, weeks before the lock: the
policy completing 12/12 vanished from the payable mid-review. Months must
also lock chronologically, LOCKED appraisals must not be deletable, and
commission_paid_total must not count draft (non-final) commissions.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType, CommissionStatus,
    FinancialImport, ImportBatch, Commission, EvQuarterAchievement,
    Appraisal, AppraisalStatus, CommissionPctTable,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def edge_setup():
    """Policy at 11/12 via legacy months — the NF of 08/2026 pays the 12th
    parcela, the exact edge where premature SETTLED used to hide the policy
    from the payable during review."""
    suffix = uuid.uuid4().hex[:8]

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

    admin = User(email=f"eg-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"eg-ev-{suffix}@x", name="EV", role=UserRole.EV, active=True)
    db.session.add_all([admin, ev])
    db.session.flush()

    client_row = Client.find_or_create(f"EGClient-{suffix}")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id=f"A-EG-{suffix}",
        hubspot_ticket_id=f"EG-{suffix}",
        numero_apolice=f"AP-EG-{suffix}",
        ev_id=ev.id, client_id=client_row.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2026, 7, 1),
        initial_installments_paid=11,
        installments_paid=11,
        commission_status=CommissionStatus.IN_PAYMENT,
    )
    db.session.add(policy)
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=3, year=2026,
        achievement_pct=Decimal("0.75"),
    ))
    db.session.flush()

    batch = ImportBatch(filename="eg.xlsx", uploaded_by=admin.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()
    nf = FinancialImport(
        import_batch_id=batch.id, month=8, year=2026,
        nf_valor_liquido=Decimal("1000.00"),
        nf_mes_recebimento="2026-08",
        cliente_mae=client_row.name,
        operadora="SulAmerica", produto="Saúde",
        numero_apolice=f"AP-EG-{suffix}",
        tipo_receita="Comissão", status_recebimento="RECEBIDO",
        data_recebimento=date(2026, 8, 10),
        match_status="UNMATCHED",
    )
    db.session.add(nf)

    appraisal = Appraisal(month=8, year=2026, status=AppraisalStatus.DRAFT,
                          created_by=admin.id)
    db.session.add(appraisal)
    db.session.commit()

    return {"admin": admin, "ev": ev, "policy": policy, "nf": nf,
            "appraisal": appraisal}


def _transition(client, headers, appraisal_id, to):
    return client.post(
        f"/api/v1/appraisals/{appraisal_id}/transition",
        json={"to": to}, headers=headers,
    )


def test_settled_only_after_lock(client, db_session, edge_setup):
    s = edge_setup
    headers = _auth_header(s["admin"])
    a_id = s["appraisal"].id

    for status in ("CALCULATING", "VALIDATING", "REVOPS_REVIEW"):
        resp = _transition(client, headers, a_id, status)
        assert resp.status_code == 200, (status, resp.get_json())
        db.session.expire_all()
        policy = db.session.get(Policy, s["policy"].id)
        # The 12th parcela is A apurar — official clock and status must not
        # move until the month LOCKs.
        assert policy.installments_paid == 11, status
        assert policy.commission_status == CommissionStatus.IN_PAYMENT, status

    # The commission for the 12th parcela was produced normally.
    assert Commission.query.filter_by(
        policy_id=s["policy"].id, month=8, year=2026,
    ).count() == 1

    resp = _transition(client, headers, a_id, "LOCKED")
    assert resp.status_code == 200
    db.session.expire_all()
    policy = db.session.get(Policy, s["policy"].id)
    assert policy.installments_paid == 12
    assert policy.commission_status == CommissionStatus.SETTLED

    # Reopen is symmetric: the month leaves the official clock again.
    resp = _transition(client, headers, a_id, "REVOPS_REVIEW")
    assert resp.status_code == 200
    db.session.expire_all()
    policy = db.session.get(Policy, s["policy"].id)
    assert policy.installments_paid == 11
    assert policy.commission_status == CommissionStatus.IN_PAYMENT


def test_months_must_lock_chronologically(client, db_session, edge_setup):
    s = edge_setup
    headers = _auth_header(s["admin"])
    april = Appraisal(month=4, year=2026, status=AppraisalStatus.REVOPS_REVIEW,
                      created_by=s["admin"].id)
    db.session.add(april)
    db.session.commit()
    may_id = s["appraisal"].id  # fixture appraisal is 08/2026 DRAFT
    # 08/2026 cannot start calculating while 04/2026 is still in review.
    resp = _transition(client, headers, may_id, "CALCULATING")
    assert resp.status_code == 422
    assert "04/2026" in resp.get_json()["error"]["message"]

    # Lock April (no earlier appraisal exists) and the gate opens.
    resp = _transition(client, headers, april.id, "LOCKED")
    assert resp.status_code == 200
    resp = _transition(client, headers, may_id, "CALCULATING")
    assert resp.status_code == 200


def test_delete_locked_appraisal_is_rejected(client, db_session, edge_setup):
    s = edge_setup
    headers = _auth_header(s["admin"])
    a = s["appraisal"]
    a.status = AppraisalStatus.LOCKED
    a.locked_at = datetime.now(timezone.utc)
    db.session.commit()

    resp = client.delete(f"/api/v1/appraisals/{a.id}", headers=headers)
    assert resp.status_code == 409
    db.session.refresh(a)
    assert a.status == AppraisalStatus.LOCKED

    # Reopen first, then delete works (reopen already pulled the month out
    # of the official totals/clock).
    resp = _transition(client, headers, a.id, "REVOPS_REVIEW")
    assert resp.status_code == 200
    resp = client.delete(f"/api/v1/appraisals/{a.id}", headers=headers)
    assert resp.status_code == 200


def test_commission_paid_total_only_counts_final(db_session, edge_setup):
    s = edge_setup
    policy = s["policy"]
    policy.commission_paid_legacy = Decimal("10.00")
    db.session.add_all([
        Commission(policy_id=policy.id, ev_id=s["ev"].id, month=1, year=2026,
                   total_actual=Decimal("100.00"), is_final=True),
        Commission(policy_id=policy.id, ev_id=s["ev"].id, month=2, year=2026,
                   total_actual=Decimal("50.00"), is_final=False),
    ])
    db.session.commit()

    # Draft (non-final) values are not "paid" — only LOCKED history + legacy.
    assert policy.commission_paid_total == Decimal("110.00")
