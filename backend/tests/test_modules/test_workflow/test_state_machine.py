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
    Policy, Client, Segment, BenefitType, Commission,
)
from app.extensions import db


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
