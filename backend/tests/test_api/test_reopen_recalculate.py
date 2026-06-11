"""Reopen + recalculate must be loss-free (#53).

The reopen (LOCKED → REVOPS_REVIEW) used to keep Commission.is_final=True,
so the next recalculate treated every policy of the month as "locked" and
demoted all its NFs to UNMATCHED with policy_id wiped — destroying the match
history the 12-month clock and paid totals are derived from. Recalculate
also rewrote values mid-review without resetting state or validations.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType,
    FinancialImport, ImportBatch, Commission, EvQuarterAchievement,
    Appraisal, AppraisalStatus, CommissionPctTable, EvValidation,
    ValidationStatus,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def flow_setup():
    """One EV + one matched-able NF for the 08/2026 apuração (gongo Q3/2026),
    with the pct table seeded — the full pipeline can run via transitions."""
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

    admin = User(email=f"rr-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"rr-ev-{suffix}@x", name="EV", role=UserRole.EV, active=True)
    db.session.add_all([admin, ev])
    db.session.flush()

    client_row = Client.find_or_create(f"RRClient-{suffix}")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id=f"A-RR-{suffix}",
        hubspot_ticket_id=f"RR-{suffix}",
        numero_apolice=f"AP-RR-{suffix}",
        ev_id=ev.id, client_id=client_row.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2026, 7, 1),
    )
    db.session.add(policy)
    db.session.add(EvQuarterAchievement(
        ev_id=ev.id, quarter=3, year=2026,
        achievement_pct=Decimal("0.75"),
    ))
    db.session.flush()

    batch = ImportBatch(filename="rr.xlsx", uploaded_by=admin.id, status="CONFIRMED")
    db.session.add(batch)
    db.session.flush()
    nf = FinancialImport(
        import_batch_id=batch.id, month=8, year=2026,
        nf_valor_liquido=Decimal("1000.00"),
        nf_mes_recebimento="2026-08",
        cliente_mae=client_row.name,
        operadora="SulAmerica", produto="Saúde",
        numero_apolice=f"AP-RR-{suffix}",
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


def _walk(client, headers, appraisal_id, *statuses):
    for s in statuses:
        resp = _transition(client, headers, appraisal_id, s)
        assert resp.status_code == 200, (s, resp.get_json())


def test_reopen_then_recalculate_preserves_matches_and_totals(
        client, db_session, flow_setup):
    s = flow_setup
    headers = _auth_header(s["admin"])
    a_id = s["appraisal"].id

    _walk(client, headers, a_id, "CALCULATING", "VALIDATING",
          "REVOPS_REVIEW", "LOCKED")
    db.session.expire_all()

    nf = db.session.get(FinancialImport, s["nf"].id)
    policy = db.session.get(Policy, s["policy"].id)
    commission = Commission.query.filter_by(policy_id=policy.id,
                                            month=8, year=2026).one()
    assert nf.match_status == "MATCHED"
    assert nf.policy_id == policy.id
    assert commission.is_final is True
    locked_total = commission.total_actual
    assert policy.total_paid_comissao == Decimal("1000.00")

    # Reopen — commissions return to recalculable, the month leaves the
    # official totals, and the match history is untouched.
    resp = _transition(client, headers, a_id, "REVOPS_REVIEW")
    assert resp.status_code == 200
    db.session.expire_all()
    commission = Commission.query.filter_by(policy_id=policy.id,
                                            month=8, year=2026).one()
    appraisal = db.session.get(Appraisal, a_id)
    nf = db.session.get(FinancialImport, s["nf"].id)
    policy = db.session.get(Policy, s["policy"].id)
    assert commission.is_final is False
    assert appraisal.locked_at is None
    assert policy.total_paid_comissao == Decimal("0")
    assert nf.match_status == "MATCHED"

    # Recalculate — the regression: this used to demote the NF to UNMATCHED
    # with policy_id wiped because is_final had survived the reopen.
    resp = client.post(f"/api/v1/appraisals/{a_id}/recalculate",
                       headers=headers)
    assert resp.status_code == 200
    db.session.expire_all()
    nf = db.session.get(FinancialImport, s["nf"].id)
    appraisal = db.session.get(Appraisal, a_id)
    assert appraisal.status == AppraisalStatus.CALCULATING
    assert nf.match_status == "MATCHED"
    assert nf.policy_id == s["policy"].id
    recalc = Commission.query.filter_by(policy_id=s["policy"].id,
                                        month=8, year=2026).one()
    assert recalc.total_actual == locked_total
    assert recalc.is_final is False

    # Close the loop: re-lock and the official totals come back identical.
    _walk(client, headers, a_id, "VALIDATING", "REVOPS_REVIEW", "LOCKED")
    db.session.expire_all()
    policy = db.session.get(Policy, s["policy"].id)
    assert policy.total_paid_comissao == Decimal("1000.00")


def test_recalculate_in_review_resets_state_and_validations(
        client, db_session, flow_setup):
    """Values only change in CALCULATING: a recalculate issued mid-review
    moves the appraisal back through the state machine and voids the
    validations attested against the old numbers."""
    s = flow_setup
    headers = _auth_header(s["admin"])
    a = s["appraisal"]
    a.status = AppraisalStatus.VALIDATING
    db.session.add(EvValidation(
        appraisal_id=a.id, policy_id=s["policy"].id, ev_id=s["ev"].id,
        status=ValidationStatus.PENDING,
    ))
    db.session.commit()

    resp = client.post(f"/api/v1/appraisals/{a.id}/recalculate",
                       headers=headers)
    assert resp.status_code == 200
    db.session.expire_all()
    appraisal = db.session.get(Appraisal, a.id)
    assert appraisal.status == AppraisalStatus.CALCULATING
    assert EvValidation.query.filter_by(appraisal_id=a.id).count() == 0


def test_recalculate_locked_is_rejected(client, db_session, flow_setup):
    s = flow_setup
    a = s["appraisal"]
    a.status = AppraisalStatus.LOCKED
    db.session.commit()

    resp = client.post(f"/api/v1/appraisals/{a.id}/recalculate",
                       headers=_auth_header(s["admin"]))
    assert resp.status_code == 409
    db.session.refresh(a)
    assert a.status == AppraisalStatus.LOCKED


def test_calculator_preserves_match_to_locked_only_candidate(
        db_session, flow_setup):
    """Defense in depth: even if a month still has is_final commissions
    (e.g. a partially locked edge), a re-run must not strip the MATCHED
    link those locked commissions were built on."""
    from app.modules.commissions.calculator import run_monthly_appraisal
    s = flow_setup
    nf, policy = s["nf"], s["policy"]
    nf.match_status = "MATCHED"
    nf.policy_id = policy.id
    db.session.add(Commission(
        policy_id=policy.id, ev_id=s["ev"].id, month=8, year=2026,
        total_actual=Decimal("60.00"), is_final=True,
    ))
    db.session.commit()

    run_monthly_appraisal(8, 2026, validate_achievements=False)
    db.session.flush()
    db.session.expire_all()

    nf = db.session.get(FinancialImport, s["nf"].id)
    assert nf.match_status == "MATCHED"
    assert nf.policy_id == s["policy"].id
