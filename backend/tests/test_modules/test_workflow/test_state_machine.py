from datetime import date
from decimal import Decimal
from unittest.mock import patch
from app.modules.workflow.state_machine import (
    start_appraisal,
    transition_appraisal,
    InvalidTransitionError,
)
from app.models import (
    Appraisal, AppraisalStatus, User, UserRole,
    Policy, Client, Segment, BenefitType, Commission, EvValidation,
    EvSignoff, SignoffStatus, ValidationStatus, CommissionStatus,
    ImportBatch, FinancialImport,
)
from app.extensions import db
from app.modules.workflow.signoffs import compute_ev_fingerprint, ensure_signoffs


def test_start_appraisal_creates_draft(db_session):
    admin = User(email="admin@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(month=1, year=2026, created_by=admin.id)
    assert appraisal.status == AppraisalStatus.DRAFT
    assert appraisal.month == 1
    assert appraisal.year == 2026


def test_transition_draft_to_calculating(db_session):
    admin = User(email="admin2@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(month=1, year=2026, created_by=admin.id)
    # Mock the calculator: this test is about the transition itself, not
    # about running a full apuracao (calculator is exercised in test_calculator_v2)
    with patch("app.modules.commissions.calculator.run_monthly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    assert appraisal.status == AppraisalStatus.CALCULATING


def test_transition_to_validating_creates_ev_validations_from_commissions(db_session):
    admin = User(
        email="validation-admin@piposaude.com",
        name="Admin",
        role=UserRole.ADMIN,
    )
    ev = User(
        email="validation-ev@piposaude.com",
        name="EV",
        role=UserRole.EV,
        active=True,
    )
    db_session.add_all([admin, ev])
    db_session.flush()

    client = Client.find_or_create("Validation Client")
    db_session.flush()
    policy = Policy(
        hubspot_ticket_id="VALIDATION-T1",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2026, 1, 1),
    )
    db_session.add(policy)
    db_session.flush()

    appraisal = Appraisal(
        month=4,
        year=2026,
        status=AppraisalStatus.CALCULATING,
        created_by=admin.id,
    )
    commission = Commission(
        policy_id=policy.id,
        ev_id=ev.id,
        month=4,
        year=2026,
        segment="M",
        achievement_pct=Decimal("0.75"),
        commission_pct=Decimal("0.06"),
        total_actual=Decimal("100.00"),
    )
    db_session.add_all([appraisal, commission])
    db_session.flush()

    # Gate de conferência (2026-07-07): a liberação para VALIDATING exige
    # sign-off DONE de todo EV do escopo.
    ensure_signoffs(appraisal)
    for _sig in EvSignoff.query.filter_by(appraisal_id=appraisal.id).all():
        _sig.status = SignoffStatus.DONE
        _sig.fingerprint = compute_ev_fingerprint(
            _sig.ev_id, appraisal.month, appraisal.year,
        )
    db.session.flush()

    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)

    validations = EvValidation.query.filter_by(appraisal_id=appraisal.id).all()
    assert len(validations) == 1
    assert validations[0].policy_id == policy.id
    assert validations[0].ev_id == ev.id
    assert validations[0].status == ValidationStatus.PENDING


def test_invalid_transition_raises(db_session):
    admin = User(email="admin3@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(month=2, year=2026, created_by=admin.id)
    try:
        # DRAFT → LOCKED is invalid (must traverse the full chain)
        transition_appraisal(appraisal, AppraisalStatus.LOCKED)
        assert False, "Should have raised InvalidTransitionError"
    except InvalidTransitionError:
        pass


def test_full_chain_to_locked(db_session):
    admin = User(email="admin4@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(month=3, year=2026, created_by=admin.id)
    # Mock the calculator: this test is about transition validation, not about
    # running a real apuracao.
    with patch("app.modules.commissions.calculator.run_monthly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    transition_appraisal(appraisal, AppraisalStatus.LIDER_REVIEW)
    transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)
    transition_appraisal(appraisal, AppraisalStatus.LOCKED, approved_by=admin.id)

    assert appraisal.status == AppraisalStatus.LOCKED


def test_lock_preserves_manual_paid_baseline(db_session):
    """Locking an apuracao must NOT overwrite the frozen manual pre-platform
    paid baseline with NF gross sums -- the NF recompute is retired. The matched
    NF below would have clobbered total_paid_comissao to 5000 under the old code.
    """
    admin = User(email="admin-lockpaid@piposaude.com", name="Admin", role=UserRole.ADMIN)
    ev = User(email="ev-lockpaid@piposaude.com", name="EV", role=UserRole.EV, active=True)
    db_session.add_all([admin, ev])
    db_session.flush()
    client = Client(name="LockCo", name_normalized="lockco", ev_id=ev.id)
    db_session.add(client)
    db_session.flush()
    policy = Policy(
        hubspot_apolice_id="LK-1", hubspot_ticket_id="LK-1",
        ev_id=ev.id, client_id=client.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        mrr_projected=Decimal("10000"), closed_date=date(2026, 3, 15),
        commission_status=CommissionStatus.IN_PAYMENT, installments_paid=1,
        total_paid_comissao=Decimal("10000.00"),  # frozen manual baseline
    )
    db_session.add(policy)
    db_session.flush()
    batch = ImportBatch(filename="f.xlsx", uploaded_by=admin.id)
    db_session.add(batch)
    db_session.flush()
    db_session.add(FinancialImport(
        policy_id=policy.id, import_batch_id=batch.id,
        nf_valor_liquido=Decimal("5000"), nf_mes_recebimento="2026-03",
        month=3, year=2026, tipo_receita="Comissão", match_status="MATCHED",
    ))
    db_session.flush()

    appraisal = start_appraisal(month=3, year=2026, created_by=admin.id)
    appraisal.status = AppraisalStatus.REVOPS_REVIEW
    db_session.flush()
    transition_appraisal(appraisal, AppraisalStatus.LOCKED, approved_by=admin.id)

    assert policy.total_paid_comissao == Decimal("10000.00")


def test_lider_review_can_send_back_to_calculating(db_session):
    admin = User(email="admin-lr@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(month=1, year=2027, created_by=admin.id)
    with patch("app.modules.commissions.calculator.run_monthly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    transition_appraisal(appraisal, AppraisalStatus.LIDER_REVIEW)
    with patch("app.modules.commissions.calculator.run_monthly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    assert appraisal.status == AppraisalStatus.CALCULATING


def test_revops_review_can_send_back_to_calculating(db_session):
    admin = User(email="admin-rr@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(month=2, year=2027, created_by=admin.id)
    with patch("app.modules.commissions.calculator.run_monthly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    transition_appraisal(appraisal, AppraisalStatus.LIDER_REVIEW)
    transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)
    with patch("app.modules.commissions.calculator.run_monthly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    assert appraisal.status == AppraisalStatus.CALCULATING


def test_locked_can_reopen_to_revops_review(db_session):
    admin = User(email="admin5@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(month=3, year=2027, created_by=admin.id)
    with patch("app.modules.commissions.calculator.run_monthly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    transition_appraisal(appraisal, AppraisalStatus.LIDER_REVIEW)
    transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)
    transition_appraisal(appraisal, AppraisalStatus.LOCKED, approved_by=admin.id)

    transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)
    assert appraisal.status == AppraisalStatus.REVOPS_REVIEW

    try:
        transition_appraisal(appraisal, AppraisalStatus.DRAFT)
        assert False, "Should have raised"
    except InvalidTransitionError:
        pass


def test_lock_marks_all_month_commissions_as_final(db_session):
    """When transitioning REVOPS_REVIEW → LOCKED, all non-final commissions
    for the apuração's (month, year) get is_final=True."""
    admin = User(email="lock-admin@piposaude.com", name="Admin",
                 role=UserRole.ADMIN, active=True)
    db.session.add(admin)
    db.session.flush()

    ev = User(email="lock-ev@piposaude.com", name="EV",
              role=UserRole.EV, active=True)
    db.session.add(ev)
    db.session.flush()

    client = Client.find_or_create("LockClient")
    db.session.flush()

    policy = Policy(
        hubspot_apolice_id="A-LOCK-T1",
        hubspot_ticket_id="LOCK-T1",
        ev_id=ev.id,
        client_id=client.id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 12, 1),
        first_payment_real=date(2026, 1, 1),
    )
    db.session.add(policy)
    db.session.flush()

    appraisal = Appraisal(
        month=4, year=2026, status=AppraisalStatus.REVOPS_REVIEW,
        created_by=admin.id,
    )
    db.session.add(appraisal)
    db.session.flush()

    comm = Commission(
        policy_id=policy.id, ev_id=ev.id, month=4, year=2026,
        segment="M", achievement_pct=Decimal("0.5"),
        commission_pct=Decimal("0.06"), commission_pct_version=1,
        monthly_actual=Decimal("100.00"), total_actual=Decimal("100.00"),
        is_final=False,
    )
    db.session.add(comm)
    db.session.flush()

    transition_appraisal(appraisal, AppraisalStatus.LOCKED, approved_by=admin.id)
    db.session.flush()

    db.session.refresh(comm)
    assert comm.is_final is True
    assert appraisal.status == AppraisalStatus.LOCKED
    assert appraisal.locked_at is not None
