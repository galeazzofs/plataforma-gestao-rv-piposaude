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

    appraisal = start_appraisal(quarter=1, year=2026, created_by=admin.id)
    assert appraisal.status == AppraisalStatus.DRAFT
    assert appraisal.quarter == 1
    assert appraisal.year == 2026


def test_transition_draft_to_calculating(db_session):
    admin = User(email="admin2@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(quarter=1, year=2026, created_by=admin.id)
    # Mock the calculator: this test is about the transition itself, not
    # about running a full apuracao (calculator is exercised in test_calculator_v2)
    with patch("app.modules.commissions.calculator.run_quarterly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    assert appraisal.status == AppraisalStatus.CALCULATING


def test_invalid_transition_raises(db_session):
    admin = User(email="admin3@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(quarter=2, year=2026, created_by=admin.id)
    try:
        # DRAFT → APPROVED is invalid
        transition_appraisal(appraisal, AppraisalStatus.APPROVED)
        assert False, "Should have raised InvalidTransitionError"
    except InvalidTransitionError:
        pass


def test_locked_appraisal_cannot_transition(db_session):
    admin = User(email="admin4@piposaude.com", name="Admin", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.flush()

    appraisal = start_appraisal(quarter=3, year=2026, created_by=admin.id)
    # Mock the calculator: this test is about transition validation, not about
    # running a real apuracao.
    with patch("app.modules.commissions.calculator.run_quarterly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    transition_appraisal(appraisal, AppraisalStatus.REVIEWING)
    transition_appraisal(appraisal, AppraisalStatus.APPROVED)
    transition_appraisal(appraisal, AppraisalStatus.LOCKED)

    try:
        transition_appraisal(appraisal, AppraisalStatus.DRAFT)
        assert False, "Should have raised"
    except InvalidTransitionError:
        pass


def test_lock_marks_all_quarter_commissions_as_final(db_session):
    """When transitioning APPROVED → LOCKED, all non-final commissions
    for the apuração's (quarter, year) get is_final=True."""
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
        quarter=4, year=2026, status=AppraisalStatus.APPROVED,
        created_by=admin.id,
    )
    db.session.add(appraisal)
    db.session.flush()

    comm = Commission(
        policy_id=policy.id, ev_id=ev.id, quarter=4, year=2026,
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
