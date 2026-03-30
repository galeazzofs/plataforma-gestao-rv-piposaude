from datetime import date, datetime, timezone
from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, EvValidation, ValidationStatus,
)


def auto_approve_expired_validations():
    """Auto-approve validations where deadline has passed.

    Runs as daily cron job.
    Returns count of auto-approved validations.
    """
    today = date.today()
    count = 0

    appraisals = Appraisal.query.filter(
        Appraisal.status == AppraisalStatus.VALIDATING,
        Appraisal.validation_deadline <= today,
    ).all()

    for appraisal in appraisals:
        pending = EvValidation.query.filter(
            EvValidation.appraisal_id == appraisal.id,
            EvValidation.status == ValidationStatus.PENDING,
        ).all()

        for validation in pending:
            validation.status = ValidationStatus.AUTO_APPROVED
            validation.resolved_at = datetime.now(timezone.utc)
            count += 1

        # If all validations are now done, advance to REVIEWING
        remaining_pending = EvValidation.query.filter(
            EvValidation.appraisal_id == appraisal.id,
            EvValidation.status == ValidationStatus.PENDING,
        ).count()

        if remaining_pending == 0:
            appraisal.status = AppraisalStatus.REVIEWING

    db.session.flush()
    return count
