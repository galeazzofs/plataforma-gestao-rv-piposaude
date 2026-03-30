from datetime import datetime, timezone
from app.extensions import db
from app.models import Appraisal, AppraisalStatus
from app.modules.workflow.transitions import VALID_TRANSITIONS


class InvalidTransitionError(Exception):
    pass


def start_appraisal(quarter, year, created_by):
    """Create a new appraisal in DRAFT status."""
    existing = Appraisal.query.filter_by(quarter=quarter, year=year).first()
    if existing:
        raise InvalidTransitionError(
            f"Appraisal for Q{quarter}/{year} already exists (status: {existing.status.value})"
        )

    appraisal = Appraisal(
        quarter=quarter,
        year=year,
        status=AppraisalStatus.DRAFT,
        created_by=created_by,
    )
    db.session.add(appraisal)
    db.session.flush()
    return appraisal


def transition_appraisal(appraisal, new_status, **kwargs):
    """Transition appraisal to a new status.

    Validates the transition is allowed.
    """
    allowed = VALID_TRANSITIONS.get(appraisal.status, [])
    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition from {appraisal.status.value} to {new_status.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )

    appraisal.status = new_status

    # Side effects
    if new_status == AppraisalStatus.LOCKED:
        appraisal.locked_at = datetime.now(timezone.utc)
        appraisal.approved_by_finance = kwargs.get("approved_by")

    if new_status == AppraisalStatus.VALIDATING:
        appraisal.validation_deadline = kwargs.get("validation_deadline")

    db.session.flush()
    return appraisal
