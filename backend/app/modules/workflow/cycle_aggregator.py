"""Build the team-grouped component status for a MonthlyCycle.

The cycle is an orchestration shell over the monthly apuração sequence:

  1. Apuração EV        — monthly Appraisal (shared across all teams)
  2. Apuração CN        — CnMonthlyAppraisal of the cycle month (per CN)

and, only on quarter-end months (3, 6, 9, 12), the quarterly bonuses:

  3. Bônus CN           — CnQuarterBonus (per CN)
  4. Bônus EV           — EvQuarterAchievement (per EV)
  5. Bônus Liderança    — LiderVendasQuarterAppraisal (per Líder)

For each team we report the per-component aggregate so the unified
cycle page can render progress per Líder de Vendas team.
"""
from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal, CnQuarterBonus,
    EvQuarterAchievement, EvValidation, LiderVendasQuarterAppraisal,
    MonthlyCycle, MonthlyCycleStatus, Team, User, UserRole,
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


def _month_appraisal(month: int, year: int):
    return Appraisal.query.filter_by(month=month, year=year).first()


def _ev_apuracao_status(appraisal, ev_ids: list) -> dict:
    """Status of the Apuração EV component, viewed for one team.

    The Appraisal is global for the month; validation progress is
    team-local (only this team's EVs count)."""
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
    return {"status": appraisal.status.value, "validations_total": total,
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


def _cn_apuracao_status(cn_ids: list, month: int, year: int) -> dict:
    if not cn_ids:
        return {"status": "PENDING", "rows": 0, "month": month}
    rows = CnMonthlyAppraisal.query.filter(
        CnMonthlyAppraisal.cn_id.in_(cn_ids),
        CnMonthlyAppraisal.year == year,
        CnMonthlyAppraisal.month == month,
    ).all()
    if not rows:
        return {"status": "PENDING", "rows": 0, "month": month}
    return {
        "status": _summarize_status_set([r.status for r in rows]),
        "rows": len(rows),
        "month": month,
    }


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


def _leadership_status(lider_id, quarter: int, year: int) -> dict:
    row = LiderVendasQuarterAppraisal.query.filter_by(
        lider_vendas_id=lider_id, quarter=quarter, year=year,
    ).first()
    if row is None:
        return {"status": "PENDING"}
    return {"status": row.status.value, "has_contestation": row.has_contestation}


def _components_for(appraisal, ev_ids, cn_ids, leader_id,
                    month: int, year: int) -> dict:
    """Components of one team's block, following the apuração sequence."""
    quarter = _quarter_of(month)
    components = {
        "ev_apuracao": _ev_apuracao_status(appraisal, ev_ids),
        "cn_apuracao": _cn_apuracao_status(cn_ids, month, year),
    }
    if month % 3 == 0:
        components["cn_bonus"] = _cn_bonus_status(cn_ids, quarter, year)
        components["ev_bonus"] = _ev_bonus_status(ev_ids, quarter, year)
        components["leadership_bonus"] = (
            _leadership_status(leader_id, quarter, year)
            if leader_id else {"status": "PENDING"}
        )
    return components


def build_cycle_payload(cycle: MonthlyCycle) -> dict:
    """Return the full per-team / per-component payload for a cycle."""
    month, year = cycle.month, cycle.year
    appraisal = _month_appraisal(month, year)

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
            "components": _components_for(
                appraisal, ev_ids, cn_ids, team.leader_id, month, year,
            ),
        })

    # CNs not assigned to any team — surface so they don't disappear.
    if unteamed_cn_ids:
        team_blocks.append({
            "team_id": None,
            "team_name": "Sem time",
            "leader_id": None,
            "ev_count": 0,
            "cn_count": len(unteamed_cn_ids),
            "components": _components_for(
                None, [], unteamed_cn_ids, None, month, year,
            ),
        })

    return {
        "id": str(cycle.id),
        "month": month,
        "year": year,
        "quarter": cycle.quarter,
        "is_quarter_end": cycle.is_quarter_end,
        "sequence": component_sequence(month),
        "status": cycle.status.value,
        "created_by": str(cycle.created_by),
        "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
        "locked_at": cycle.locked_at.isoformat() if cycle.locked_at else None,
        "teams": team_blocks,
    }


def all_components_locked(cycle: MonthlyCycle) -> bool:
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
