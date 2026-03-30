from datetime import date
from app.modules.workflow.state_machine import (
    start_appraisal,
    transition_appraisal,
    InvalidTransitionError,
)
from app.models import Appraisal, AppraisalStatus, User, UserRole
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
