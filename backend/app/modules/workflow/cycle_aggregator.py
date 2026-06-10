"""Build the global component status for a MonthlyCycle.

The cycle is an orchestration shell over the monthly apuração sequence:

  1. Apuração EV        — monthly Appraisal (one per month)
  2. Apuração CN        — CnMonthlyAppraisal of the cycle month (per CN)

and, only on quarter-end months (3, 6, 9, 12), the quarterly bonuses:

  3. Bônus CN           — CnQuarterBonus (per CN)
  4. Bônus EV           — EvQuarterAchievement (per EV)
  5. Bônus Liderança    — LiderVendasQuarterAppraisal (per Líder)

Components are aggregated globally — there is no per-team partition.
Each component also reports `expected` (eligible-user count) where rows
are per-user: an all-LOCKED set that misses an eligible user must not
read LOCKED, otherwise the cycle could auto-close with work missing.
"""
from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal, CnQuarterBonus,
    EvQuarterAchievement, EvValidation, LiderVendasQuarterAppraisal,
    MonthlyCycle, MonthlyCycleStatus, User, UserRole,
    ValidationStatus,
)


BASE_SEQUENCE = ["ev_apuracao", "cn_apuracao"]
QUARTER_END_SEQUENCE = BASE_SEQUENCE + ["cn_bonus", "ev_bonus", "leadership_bonus"]


def component_sequence(month: int) -> list:
    """Ordered component keys for a cycle month. Quarterly bonuses only
    exist on the last month of each quarter."""
    return QUARTER_END_SEQUENCE if month % 3 == 0 else BASE_SEQUENCE


def _quarter_of(month: int) -> int:
    return (month - 1) // 3 + 1


def _active_count(role: UserRole, exclude_left: bool = False) -> int:
    q = User.query.filter_by(role=role, active=True)
    if exclude_left:
        q = q.filter_by(left_company=False)
    return q.count()


def _ev_apuracao_status(month: int, year: int) -> dict:
    """Status of the Apuração EV component: the month's Appraisal plus
    its global validation progress."""
    appraisal = Appraisal.query.filter_by(month=month, year=year).first()
    if appraisal is None:
        return {"status": "PENDING", "appraisal_id": None,
                "validations_total": 0, "validations_done": 0,
                "has_contestation": False}

    validations = EvValidation.query.filter_by(
        appraisal_id=appraisal.id,
    ).all()
    done = sum(
        1 for v in validations
        if v.status in (
            ValidationStatus.APPROVED, ValidationStatus.AUTO_APPROVED,
            ValidationStatus.RESOLVED,
        )
    )
    return {
        "status": appraisal.status.value,
        "appraisal_id": str(appraisal.id),
        "validations_total": len(validations),
        "validations_done": done,
        "has_contestation": bool(getattr(appraisal, "has_contestation", False)),
    }


def _summarize_status_set(statuses: list) -> str:
    """Reduce a list of component-row statuses into one status.

    Rules:
      - empty / no rows → PENDING
      - all LOCKED → LOCKED
      - any in REVOPS_REVIEW → REVOPS_REVIEW
      - any in LIDER_REVIEW → LIDER_REVIEW
      - any in VALIDATING → VALIDATING
      - any in CALCULATING → CALCULATING
      - else → DRAFT
    """
    if not statuses:
        return "PENDING"
    s = set(statuses)
    if s == {AppraisalStatus.LOCKED}:
        return "LOCKED"
    for level in (
        AppraisalStatus.REVOPS_REVIEW,
        AppraisalStatus.LIDER_REVIEW,
        AppraisalStatus.VALIDATING,
        AppraisalStatus.CALCULATING,
    ):
        if level in s:
            return level.value
    return "DRAFT"


def _hold_open_if_incomplete(status: str, rows: int, expected: int) -> str:
    """An all-LOCKED row set that misses an eligible user is not done:
    someone's apuração was never created. Hold the component open."""
    if status == "LOCKED" and rows < expected:
        return "CALCULATING"
    return status


def _cn_apuracao_status(month: int, year: int, hold_open: bool = True) -> dict:
    expected = _active_count(UserRole.CN)
    rows = CnMonthlyAppraisal.query.filter_by(year=year, month=month).all()
    if not rows:
        return {"status": "PENDING", "rows": 0, "expected": expected,
                "month": month, "has_contestation": False}
    status = _summarize_status_set([r.status for r in rows])
    if hold_open:
        status = _hold_open_if_incomplete(status, len(rows), expected)
    return {
        "status": status,
        "rows": len(rows),
        "expected": expected,
        "month": month,
        "has_contestation": any(r.has_contestation for r in rows),
    }


def _bonus_rows_status(rows: list, expected: int, hold_open: bool = True) -> dict:
    final = sum(1 for r in rows if r.is_final)
    if not rows:
        return {"status": "PENDING", "rows": 0, "final": 0,
                "expected": expected}
    status = "LOCKED" if all(r.is_final for r in rows) else "CALCULATING"
    if hold_open:
        status = _hold_open_if_incomplete(status, len(rows), expected)
    return {
        "status": status,
        "rows": len(rows),
        "final": final,
        "expected": expected,
    }


def _cn_bonus_status(quarter: int, year: int, hold_open: bool = True) -> dict:
    rows = CnQuarterBonus.query.filter_by(quarter=quarter, year=year).all()
    return _bonus_rows_status(rows, _active_count(UserRole.CN), hold_open)


def _ev_bonus_status(quarter: int, year: int, hold_open: bool = True) -> dict:
    rows = EvQuarterAchievement.query.filter_by(
        quarter=quarter, year=year,
    ).all()
    return _bonus_rows_status(
        rows, _active_count(UserRole.EV, exclude_left=True), hold_open,
    )


def _leadership_status(quarter: int, year: int, hold_open: bool = True) -> dict:
    expected = _active_count(UserRole.LIDER_VENDAS)
    rows = LiderVendasQuarterAppraisal.query.filter_by(
        quarter=quarter, year=year,
    ).all()
    if not rows:
        return {"status": "PENDING", "rows": 0, "expected": expected,
                "appraisal_id": None, "has_contestation": False}
    status = _summarize_status_set([r.status for r in rows])
    if hold_open:
        status = _hold_open_if_incomplete(status, len(rows), expected)
    return {
        "status": status,
        "rows": len(rows),
        "expected": expected,
        # The inline transition buttons need a row id; with the single
        # Líder P/M there is exactly one. Ambiguous (2+) → None, the UI
        # falls back to the detail page.
        "appraisal_id": str(rows[0].id) if len(rows) == 1 else None,
        "has_contestation": any(r.has_contestation for r in rows),
    }


def _components(cycle: MonthlyCycle) -> dict:
    month, year = cycle.month, cycle.year
    quarter = _quarter_of(month)
    # A LOCKED cycle is frozen history: `expected` reflects the CURRENT
    # user table, so the incompleteness guard would falsely reopen
    # components after team changes. Only enforce it while OPEN.
    hold_open = cycle.status != MonthlyCycleStatus.LOCKED
    components = {
        "ev_apuracao": _ev_apuracao_status(month, year),
        "cn_apuracao": _cn_apuracao_status(month, year, hold_open),
    }
    if month % 3 == 0:
        components["cn_bonus"] = _cn_bonus_status(quarter, year, hold_open)
        components["ev_bonus"] = _ev_bonus_status(quarter, year, hold_open)
        components["leadership_bonus"] = _leadership_status(
            quarter, year, hold_open,
        )
    return components


def build_cycle_payload(cycle: MonthlyCycle) -> dict:
    """Return the global per-component payload for a cycle."""
    return {
        "id": str(cycle.id),
        "month": cycle.month,
        "year": cycle.year,
        "quarter": cycle.quarter,
        "is_quarter_end": cycle.is_quarter_end,
        "sequence": component_sequence(cycle.month),
        "status": cycle.status.value,
        "created_by": str(cycle.created_by),
        "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
        "locked_at": cycle.locked_at.isoformat() if cycle.locked_at else None,
        "components": _components(cycle),
    }


def all_components_locked(cycle: MonthlyCycle) -> bool:
    """True iff every component in the cycle is LOCKED. PENDING counts as
    not-locked: a cycle with no work in a component must not auto-LOCK."""
    payload = build_cycle_payload(cycle)
    return all(
        comp.get("status") == "LOCKED"
        for comp in payload["components"].values()
    )


def maybe_lock_cycle(cycle: MonthlyCycle) -> bool:
    """Auto-LOCK the cycle if every component is LOCKED. Returns True
    when the cycle transitioned to LOCKED in this call."""
    from datetime import datetime, timezone
    if cycle.status == MonthlyCycleStatus.LOCKED:
        return False
    if not all_components_locked(cycle):
        return False
    cycle.status = MonthlyCycleStatus.LOCKED
    cycle.locked_at = datetime.now(timezone.utc)
    db.session.flush()
    return True
