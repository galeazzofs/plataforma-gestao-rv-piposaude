from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal,
    Commission, EvValidation, LiderVendasQuarterAppraisal,
    Team, User, UserRole, ValidationStatus,
)
from app.modules.workflow.transitions import VALID_TRANSITIONS


class InvalidTransitionError(Exception):
    pass


# Statuses that count as "the Líder validated own Comissão Liderança" —
# anything past VALIDATING means the Líder moved their own row forward.
_LIDER_VALIDATED_OWN = {
    AppraisalStatus.LIDER_REVIEW,
    AppraisalStatus.REVOPS_REVIEW,
    AppraisalStatus.LOCKED,
}

_VALIDATION_DONE = (
    ValidationStatus.APPROVED,
    ValidationStatus.AUTO_APPROVED,
    ValidationStatus.RESOLVED,
)


def start_appraisal(month, year, created_by):
    """Create a new appraisal in DRAFT status."""
    existing = Appraisal.query.filter_by(month=month, year=year).first()
    if existing:
        raise InvalidTransitionError(
            f"Appraisal for {month:02d}/{year} already exists (status: {existing.status.value})"
        )

    appraisal = Appraisal(
        month=month,
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
    if (
        appraisal.status == AppraisalStatus.VALIDATING
        and new_status == AppraisalStatus.REVOPS_REVIEW
        and not _required_lider_ids_for_appraisal(appraisal)
    ):
        allowed = [*allowed, AppraisalStatus.REVOPS_REVIEW]
    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition from {appraisal.status.value} to {new_status.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )

    # Issue #36: VALIDATING → LIDER_REVIEW is blocked while a contestation
    # is open. Use the contest endpoint to route to REVOPS_REVIEW instead.
    if (
        appraisal.status == AppraisalStatus.VALIDATING
        and new_status == AppraisalStatus.LIDER_REVIEW
        and getattr(appraisal, "has_contestation", False)
    ):
        raise InvalidTransitionError(
            "Cannot advance to LIDER_REVIEW while a contestation is open. "
            "Resolve the contestation first."
        )

    if (
        appraisal.status == AppraisalStatus.VALIDATING
        and new_status == AppraisalStatus.REVOPS_REVIEW
        and _required_lider_ids_for_appraisal(appraisal)
    ):
        raise InvalidTransitionError(
            "Cannot skip LIDER_REVIEW while current EVs still require "
            "sales-leader approval."
        )

    old_status = appraisal.status
    appraisal.status = new_status

    # Side effects
    if new_status == AppraisalStatus.CALCULATING:
        # Run the synchronous calculator. Status stays in CALCULATING —
        # RevOps reviews and releases manually via "Liberar para Validação".
        # Missing achievements do NOT block the apuração: affected policies fall
        # back to 0% and the gaps surface as a warning in the review payload, so
        # RevOps can fill them and recalculate before locking.
        from app.modules.commissions.calculator import run_monthly_appraisal
        run_monthly_appraisal(
            appraisal.month, appraisal.year, validate_achievements=False
        )

    if new_status == AppraisalStatus.VALIDATING:
        deadline = kwargs.get("validation_deadline")
        if deadline is None:
            deadline = (datetime.now(timezone.utc) + timedelta(days=5)).date()
        appraisal.validation_deadline = deadline
        _auto_approve_left_company_validations(appraisal)

    if new_status == AppraisalStatus.LOCKED:
        appraisal.locked_at = datetime.now(timezone.utc)
        appraisal.approved_by_finance = kwargs.get("approved_by")
        # Mark all non-final commissions of this apuração as final
        Commission.query.filter_by(
            month=appraisal.month,
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
            appraisal.month, appraisal.year
        )

    # Reset reminder state on every transition: a fresh action zeroes
    # the timer and clears any "reminder sent today" flag so the next
    # idle period starts cleanly.
    appraisal.last_action_at = datetime.now(timezone.utc)
    appraisal.reminder_sent_at = None

    db.session.flush()

    # Slack hooks — every send is wrapped so transitions never break on a
    # transport failure. Issue #38.
    _emit_appraisal_slack(appraisal, old_status, new_status)

    if new_status == AppraisalStatus.LOCKED:
        # The cycle stays quarterly; map this monthly appraisal to its quarter.
        _maybe_lock_attached_cycle((appraisal.month - 1) // 3 + 1, appraisal.year)

    return appraisal


def _maybe_lock_attached_cycle(quarter: int, year: int):
    """Re-evaluate the QuarterlyCycle for (quarter, year) and auto-LOCK if
    every component is now LOCKED. Emits the cycle-locked Slack
    notification when the cycle transitions in this call. Called from any
    component that reaches LOCKED."""
    from app.models import QuarterlyCycle
    from app.modules.workflow.cycle_aggregator import maybe_lock_cycle
    cycle = QuarterlyCycle.query.filter_by(
        quarter=quarter, year=year,
    ).first()
    if cycle is None:
        return
    locked_now = maybe_lock_cycle(cycle)
    if locked_now:
        _safe_slack(
            "notify_cycle_locked",
            lambda: _import_slack().notify_cycle_locked(quarter, year),
        )


def transition_lider_vendas_appraisal(
    appraisal: LiderVendasQuarterAppraisal, new_status,
):
    """Transition a Líder de Vendas quarterly appraisal between
    AppraisalStatus values, sharing VALID_TRANSITIONS with the other
    components.
    """
    allowed = VALID_TRANSITIONS.get(appraisal.status, [])
    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition leadership appraisal from "
            f"{appraisal.status.value} to {new_status.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )

    # Issue #36: defense-in-depth — block VALIDATING → LIDER_REVIEW while a
    # contestation is open on this row. The contest endpoint forces a
    # direct write to REVOPS_REVIEW, so this guard is normally unreachable
    # but is kept so future code paths can't smuggle past the gate.
    if (
        appraisal.status == AppraisalStatus.VALIDATING
        and new_status == AppraisalStatus.LIDER_REVIEW
        and getattr(appraisal, "has_contestation", False)
    ):
        raise InvalidTransitionError(
            "Cannot advance to LIDER_REVIEW while a contestation is open. "
            "Resolve the contestation first."
        )

    appraisal.status = new_status
    appraisal.last_action_at = datetime.now(timezone.utc)
    appraisal.reminder_sent_at = None
    db.session.flush()

    if new_status == AppraisalStatus.LOCKED:
        _maybe_lock_attached_cycle(appraisal.quarter, appraisal.year)

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

    # Issue #36: same contestation guard as LiderVendas.
    if (
        appraisal.status == AppraisalStatus.VALIDATING
        and new_status == AppraisalStatus.LIDER_REVIEW
        and getattr(appraisal, "has_contestation", False)
    ):
        raise InvalidTransitionError(
            "Cannot advance to LIDER_REVIEW while a contestation is open. "
            "Resolve the contestation first."
        )

    appraisal.status = new_status
    appraisal.last_action_at = datetime.now(timezone.utc)
    appraisal.reminder_sent_at = None
    db.session.flush()

    if new_status == AppraisalStatus.LOCKED:
        # CnMonthlyAppraisal is one of the 5 cycle components, so its
        # last LOCK should re-evaluate the cycle for this row's
        # (quarter, year). Last quarter month maps via the cycle aggregator.
        quarter = (appraisal.month - 1) // 3 + 1
        _maybe_lock_attached_cycle(quarter, appraisal.year)

    return appraisal


# ── Slack helpers ─────────────────────────────────────────────────────


def _import_slack():
    from app.modules.notifications import slack
    return slack


def _safe_slack(label: str, fn):
    try:
        fn()
    except Exception as e:  # pragma: no cover — graceful failure
        import logging
        logging.getLogger(__name__).warning(
            f"Slack {label} failed: {e}"
        )


def _emit_appraisal_slack(appraisal: Appraisal,
                          old_status: AppraisalStatus,
                          new_status: AppraisalStatus):
    """Emit Slack notifications for each meaningful Appraisal transition.
    All sends are graceful (never raise)."""
    month, year = appraisal.month, appraisal.year

    # CALCULATING → VALIDATING: DM each EV with an EvValidation row.
    if (old_status == AppraisalStatus.CALCULATING
            and new_status == AppraisalStatus.VALIDATING):
        ev_ids = {
            v.ev_id for v in EvValidation.query
            .filter_by(appraisal_id=appraisal.id).all()
        }
        if ev_ids:
            evs = User.query.filter(
                User.id.in_(ev_ids),
                User.left_company.is_(False),
            ).all()
            slack = _import_slack()
            for ev in evs:
                _safe_slack(
                    "notify_validating_released",
                    lambda u=ev: slack.notify_validating_released(
                        u, "ev_quarter", month, year,
                    ),
                )

    # LIDER_REVIEW → REVOPS_REVIEW: ops channel, "Líder approved".
    if (old_status == AppraisalStatus.LIDER_REVIEW
            and new_status == AppraisalStatus.REVOPS_REVIEW):
        # Pick a Líder name to attribute. If we have an exact "approver"
        # we'd surface them; for now report the team Líderes generically.
        names = [
            l.name for l in User.query.filter_by(
                role=UserRole.LIDER_VENDAS, active=True,
            ).all()
        ]
        attribution = ", ".join(names) if names else "Líder de Vendas"
        _safe_slack(
            "notify_lider_approved",
            lambda: _import_slack().notify_lider_approved(
                month, year, attribution,
            ),
        )

    # REVOPS_REVIEW → LOCKED: finance channel, "ready for finance"
    # NOTE: this fires *before* the cycle-locked DM fan-out, which is
    # correct — Finance hears "ready" the moment Finance themselves close.
    if (old_status == AppraisalStatus.REVOPS_REVIEW
            and new_status == AppraisalStatus.LOCKED):
        _safe_slack(
            "notify_revops_approved",
            lambda: _import_slack().notify_revops_approved(month, year),
        )


# ── Auto-advance helpers (issue #37a) ─────────────────────────────────


def _team_ev_ids(team_id) -> list:
    return [
        u.id for u in User.query.filter_by(
            team_id=team_id, role=UserRole.EV, active=True,
            left_company=False,
        ).all()
    ]


def _team_validations_complete(appraisal_id, ev_ids: list) -> tuple:
    """Return (total, done) EvValidation counts for the given EV cohort."""
    if not ev_ids:
        return (0, 0)
    rows = EvValidation.query.filter(
        EvValidation.appraisal_id == appraisal_id,
        EvValidation.ev_id.in_(ev_ids),
    ).all()
    total = len(rows)
    done = sum(1 for v in rows if v.status in _VALIDATION_DONE)
    return (total, done)


def _required_lideres_validated_own(
    quarter: int, year: int, lider_ids: set,
) -> bool:
    """True iff every required sales leader has validated own row."""
    if not lider_ids:
        return True
    for lider_id in lider_ids:
        own = LiderVendasQuarterAppraisal.query.filter_by(
            lider_vendas_id=lider_id, quarter=quarter, year=year,
        ).first()
        if own is None or own.status not in _LIDER_VALIDATED_OWN:
            return False
    return True


def _required_lider_ids_for_appraisal(appraisal: Appraisal) -> set:
    """Sales leaders responsible for current-company EV validations.

    EVs flagged as left_company stay commissionable, but RevOps owns
    their approval instead of Sales Leadership.
    """
    rows = (
        db.session.query(User.team_id)
        .join(EvValidation, EvValidation.ev_id == User.id)
        .filter(
            EvValidation.appraisal_id == appraisal.id,
            User.role == UserRole.EV,
            User.active.is_(True),
            User.left_company.is_(False),
            User.team_id.isnot(None),
        )
        .distinct()
        .all()
    )
    team_ids = [team_id for (team_id,) in rows if team_id is not None]
    if not team_ids:
        return set()
    teams = Team.query.filter(
        Team.id.in_(team_ids),
        Team.leader_id.isnot(None),
    ).all()
    return {team.leader_id for team in teams}


def _auto_approve_left_company_validations(appraisal: Appraisal) -> int:
    """Mark departed EV validations as done when RevOps releases the cycle."""
    rows = (
        EvValidation.query
        .join(User, EvValidation.ev_id == User.id)
        .filter(
            EvValidation.appraisal_id == appraisal.id,
            EvValidation.status == ValidationStatus.PENDING,
            User.role == UserRole.EV,
            User.left_company.is_(True),
        )
        .all()
    )
    now = datetime.now(timezone.utc)
    for validation in rows:
        validation.status = ValidationStatus.AUTO_APPROVED
        validation.resolved_at = now
        validation.resolution_comment = (
            "Autoaprovado: EV saiu da empresa; aprovacao fica com RevOps."
        )
    return len(rows)


def maybe_auto_advance_appraisal_after_validation(appraisal: Appraisal):
    """Hook called after an EvValidation is approved/resolved or after a
    Líder advances their own LiderVendasQuarterAppraisal. Auto-transitions
    the global Appraisal out of VALIDATING iff:

      1. Every EvValidation on the appraisal is APPROVED/AUTO_APPROVED/
         RESOLVED.
      2. Every required Líder has moved their own
         LiderVendasQuarterAppraisal past VALIDATING for this
         (quarter, year). If none are required, it goes to REVOPS_REVIEW.

    Required leaders get a chance to validate own before the global
    review gate opens. Returns True iff the appraisal advanced in this
    call.
    """
    if appraisal.status != AppraisalStatus.VALIDATING:
        return False
    if getattr(appraisal, "has_contestation", False):
        return False  # blocked by guard anyway, but skip the check

    rows = EvValidation.query.filter_by(appraisal_id=appraisal.id).all()
    if not rows:
        return False
    if not all(v.status in _VALIDATION_DONE for v in rows):
        return False

    required_lider_ids = _required_lider_ids_for_appraisal(appraisal)
    if not required_lider_ids:
        transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)
        return True
    if not _required_lideres_validated_own(
        (appraisal.month - 1) // 3 + 1, appraisal.year, required_lider_ids,
    ):
        return False

    transition_appraisal(appraisal, AppraisalStatus.LIDER_REVIEW)
    return True


def maybe_dm_lider_team_validated(appraisal: Appraisal, team_id) -> bool:
    """After a team's last EvValidation is approved, DM that team's Líder
    so they know they can review. Returns True iff the DM was queued."""
    if team_id is None:
        return False
    team = db.session.get(Team, team_id)
    if team is None or team.leader_id is None:
        return False
    ev_ids = _team_ev_ids(team_id)
    total, done = _team_validations_complete(appraisal.id, ev_ids)
    if total == 0 or done < total:
        return False
    lider = db.session.get(User, team.leader_id)
    if lider is None:
        return False
    _safe_slack(
        "notify_team_validated_for_lider",
        lambda: _import_slack().notify_team_validated_for_lider(
            lider, appraisal.month, appraisal.year,
        ),
    )
    return True
