"""Build the team-grouped component status for a QuarterlyCycle.

The cycle is an orchestration shell over five trimestral components:

  1. Comissão EV          — quarterly Appraisal (shared across all teams)
  2. Bônus EV             — EvQuarterAchievement (per EV)
  3. Bônus CN             — CnQuarterBonus (per CN)
  4. Comissão CN mês 3    — CnMonthlyAppraisal of the last quarter month
  5. Comissão Liderança   — LiderVendasQuarterAppraisal (per Líder)

For each team we report the per-component aggregate so the unified
cycle page can render progress per Líder de Vendas team.
"""
from collections import defaultdict
from typing import Optional

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal, CnQuarterBonus,
    EvQuarterAchievement, EvValidation, LiderVendasQuarterAppraisal,
    QuarterlyCycle, QuarterlyCycleStatus, Team, User, UserRole,
    ValidationStatus,
)


_LAST_MONTH_OF_QUARTER = {1: 3, 2: 6, 3: 9, 4: 12}


def _appraisal_for(quarter: int, year: int) -> Optional[Appraisal]:
    return Appraisal.query.filter_by(quarter=quarter, year=year).first()


def _ev_appraisal_status(appraisal: Optional[Appraisal], ev_ids: list) -> dict:
    """Status of the shared Comissão EV component, viewed for one team.

    The Appraisal itself is global per quarter; the team-local progress
    is computed from the EvValidations of its members.
    """
    if appraisal is None or not ev_ids:
        return {"status": "PENDING", "validations_total": 0,
                "validations_done": 0}

    validations = EvValidation.query.filter(
        EvValidation.appraisal_id == appraisal.id,
        EvValidation.ev_id.in_(ev_ids),
    ).all()
    total = len(validations)
    done = sum(
        1 for v in validations
        if v.status in (
            ValidationStatus.APPROVED, ValidationStatus.AUTO_APPROVED,
            ValidationStatus.RESOLVED,
        )
    )
    # Use the global Appraisal status as the upper bound.
    status = appraisal.status.value
    return {"status": status, "validations_total": total,
            "validations_done": done}


def _summarize_status_set(statuses: list) -> str:
    """Reduce a list of component-row statuses into one team-level status.

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


def _ev_bonus_status(ev_ids: list, quarter: int, year: int) -> dict:
    if not ev_ids:
        return {"status": "PENDING", "rows": 0, "final": 0}
    rows = EvQuarterAchievement.query.filter(
        EvQuarterAchievement.ev_id.in_(ev_ids),
        EvQuarterAchievement.quarter == quarter,
        EvQuarterAchievement.year == year,
    ).all()
    final = sum(1 for r in rows if r.is_final)
    if not rows:
        return {"status": "PENDING", "rows": 0, "final": 0}
    return {
        "status": "LOCKED" if all(r.is_final for r in rows) else "CALCULATING",
        "rows": len(rows),
        "final": final,
    }


def _cn_bonus_status(cn_ids: list, quarter: int, year: int) -> dict:
    if not cn_ids:
        return {"status": "PENDING", "rows": 0, "final": 0}
    rows = CnQuarterBonus.query.filter(
        CnQuarterBonus.cn_id.in_(cn_ids),
        CnQuarterBonus.quarter == quarter,
        CnQuarterBonus.year == year,
    ).all()
    final = sum(1 for r in rows if r.is_final)
    if not rows:
        return {"status": "PENDING", "rows": 0, "final": 0}
    return {
        "status": "LOCKED" if all(r.is_final for r in rows) else "CALCULATING",
        "rows": len(rows),
        "final": final,
    }


def _cn_last_month_status(cn_ids: list, quarter: int, year: int) -> dict:
    last_month = _LAST_MONTH_OF_QUARTER[quarter]
    if not cn_ids:
        return {"status": "PENDING", "rows": 0, "month": last_month}
    rows = CnMonthlyAppraisal.query.filter(
        CnMonthlyAppraisal.cn_id.in_(cn_ids),
        CnMonthlyAppraisal.year == year,
        CnMonthlyAppraisal.month == last_month,
    ).all()
    if not rows:
        return {"status": "PENDING", "rows": 0, "month": last_month}
    return {
        "status": _summarize_status_set([r.status for r in rows]),
        "rows": len(rows),
        "month": last_month,
    }


def _leadership_status(lider_id, quarter: int, year: int) -> dict:
    row = LiderVendasQuarterAppraisal.query.filter_by(
        lider_vendas_id=lider_id, quarter=quarter, year=year,
    ).first()
    if row is None:
        return {"status": "PENDING"}
    return {"status": row.status.value, "has_contestation": row.has_contestation}


def build_cycle_payload(cycle: QuarterlyCycle) -> dict:
    """Return the full per-team / per-component payload for a cycle."""
    quarter, year = cycle.quarter, cycle.year
    appraisal = _appraisal_for(quarter, year)

    teams = Team.query.order_by(Team.name).all()
    cn_users = User.query.filter_by(
        role=UserRole.CN, active=True,
    ).order_by(User.name).all()
    unteamed_cn_ids = [u.id for u in cn_users if u.team_id is None]

    team_blocks = []
    for team in teams:
        members = User.query.filter_by(team_id=team.id, active=True).all()
        ev_ids = [
            m.id for m in members
            if m.role == UserRole.EV and not m.left_company
        ]
        cn_ids = [m.id for m in members if m.role == UserRole.CN]

        team_blocks.append({
            "team_id": str(team.id),
            "team_name": team.name,
            "leader_id": str(team.leader_id) if team.leader_id else None,
            "ev_count": len(ev_ids),
            "cn_count": len(cn_ids),
            "components": {
                "ev_quarter":     _ev_appraisal_status(appraisal, ev_ids),
                "ev_quarterly_bonus": _ev_bonus_status(ev_ids, quarter, year),
                "cn_quarterly_bonus": _cn_bonus_status(cn_ids, quarter, year),
                "cn_monthly":     _cn_last_month_status(cn_ids, quarter, year),
                "leadership":     (
                    _leadership_status(team.leader_id, quarter, year)
                    if team.leader_id else {"status": "PENDING"}
                ),
            },
        })

    # CNs not assigned to any team — surface so they don't disappear.
    if unteamed_cn_ids:
        team_blocks.append({
            "team_id": None,
            "team_name": "Sem time",
            "leader_id": None,
            "ev_count": 0,
            "cn_count": len(unteamed_cn_ids),
            "components": {
                "ev_quarter":     {"status": "PENDING",
                                    "validations_total": 0, "validations_done": 0},
                "ev_quarterly_bonus": {"status": "PENDING", "rows": 0, "final": 0},
                "cn_quarterly_bonus": _cn_bonus_status(unteamed_cn_ids, quarter, year),
                "cn_monthly":     _cn_last_month_status(unteamed_cn_ids, quarter, year),
                "leadership":     {"status": "PENDING"},
            },
        })

    return {
        "id": str(cycle.id),
        "quarter": quarter,
        "year": year,
        "status": cycle.status.value,
        "created_by": str(cycle.created_by),
        "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
        "locked_at": cycle.locked_at.isoformat() if cycle.locked_at else None,
        "teams": team_blocks,
    }


def all_components_locked(cycle: QuarterlyCycle) -> bool:
    """True iff every component on every team in the cycle is LOCKED."""
    payload = build_cycle_payload(cycle)
    for team in payload["teams"]:
        for comp in team["components"].values():
            # PENDING is treated as not-locked even though there is
            # nothing to lock — the cycle should not auto-LOCK on a team
            # that has no work in it.
            if comp.get("status") != "LOCKED":
                return False
    return True


def maybe_lock_cycle(cycle: QuarterlyCycle) -> bool:
    """Auto-LOCK the cycle if every component is LOCKED. Returns True
    when the cycle transitioned to LOCKED in this call."""
    from datetime import datetime, timezone
    if cycle.status == QuarterlyCycleStatus.LOCKED:
        return False
    if not all_components_locked(cycle):
        return False
    cycle.status = QuarterlyCycleStatus.LOCKED
    cycle.locked_at = datetime.now(timezone.utc)
    db.session.flush()
    return True
