from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.models import Appraisal, AppraisalStatus, CnMonthlyAppraisal, Commission
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
    if new_status == AppraisalStatus.CALCULATING:
        # Run the synchronous calculator. Status stays in CALCULATING —
        # RevOps reviews and releases manually via "Liberar para Validação".
        from app.modules.commissions.calculator import run_quarterly_appraisal
        run_quarterly_appraisal(appraisal.quarter, appraisal.year)

    if new_status == AppraisalStatus.LOCKED:
        appraisal.locked_at = datetime.now(timezone.utc)
        appraisal.approved_by_finance = kwargs.get("approved_by")
        # Mark all non-final commissions of this apuração as final
        Commission.query.filter_by(
            quarter=appraisal.quarter,
            year=appraisal.year,
            is_final=False,
        ).update({"is_final": True}, synchronize_session=False)
        # Roll the Σ NF amounts (split by tipo_receita) into Policy.total_paid_*.
        # Recomputes from scratch across all locked apurações, so re-locking
        # or rerunning this step is idempotent.
        from app.modules.financial.policy_paid_totals import (
            recompute_policy_paid_totals_for_apuracao,
        )
        recompute_policy_paid_totals_for_apuracao(
            appraisal.quarter, appraisal.year
        )

    if new_status == AppraisalStatus.VALIDATING:
        deadline = kwargs.get("validation_deadline")
        if deadline is None:
            deadline = (datetime.now(timezone.utc) + timedelta(days=5)).date()
        appraisal.validation_deadline = deadline

    db.session.flush()
    return appraisal


def transition_cn_monthly_appraisal(appraisal: CnMonthlyAppraisal, new_status):
    """Transition a CN monthly appraisal between AppraisalStatus values.

    Uses the same VALID_TRANSITIONS map as the quarterly appraisal — the
    state graph is identical (DRAFT → CALCULATING → VALIDATING →
    LIDER_REVIEW → REVOPS_REVIEW → LOCKED, with reopen and recalculate
    branches).
    """
    allowed = VALID_TRANSITIONS.get(appraisal.status, [])
    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition CN appraisal from {appraisal.status.value} "
            f"to {new_status.value}. Allowed: {[s.value for s in allowed]}"
        )

    appraisal.status = new_status
    db.session.flush()
    return appraisal
