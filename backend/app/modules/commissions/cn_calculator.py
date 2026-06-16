"""CN monthly apuração runner.

Calls simulate_cn() for each active CN with a CnMonthlyGoal for the
given (month, year), persists results to CnMonthlyAppraisal.
"""
from decimal import Decimal

from app.extensions import db
from app.models import (
    AppraisalStatus, User, UserRole, CnMonthlyGoal, CnMonthlyAppraisal,
    PlatformSetting,
)
from app.modules.commissions.simulator import simulate_cn, vidas_meta_from_sao


RAMPAGEM_BONUS_SAO_KEY = "cn_rampagem_bonus_sao"
DEFAULT_RAMPAGEM_BONUS_SAO = Decimal("300")


def get_rampagem_bonus_sao() -> Decimal:
    """Configurable SAO-fora-da-meta bonus (R$ por SAO). Default 300."""
    raw = PlatformSetting.get(RAMPAGEM_BONUS_SAO_KEY, None)
    if raw in (None, ""):
        return DEFAULT_RAMPAGEM_BONUS_SAO
    try:
        return Decimal(str(raw))
    except (ValueError, ArithmeticError):
        return DEFAULT_RAMPAGEM_BONUS_SAO


class MissingGoalsError(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Missing CN goals: {missing}")


def _vidas_meta_for(cn, goal):
    """Lives target derived from the CN porte (SAO × factor), exactly like
    the simulator. Falls back to the goal's stored vidas_target only when
    porte is unset or the derived value is non-positive."""
    porte = cn.porte.value if hasattr(cn.porte, "value") else cn.porte
    auto = vidas_meta_from_sao(Decimal(str(goal.sao_target)), porte)
    if auto and auto > 0:
        return auto
    return Decimal(str(goal.vidas_target))


def validate_cn_goals(month: int, year: int) -> list[str]:
    """Return list of '<name> → <month>/<year>' for active CNs missing a goal."""
    active_cns = User.query.filter_by(role=UserRole.CN, active=True).all()
    missing = []
    for cn in active_cns:
        goal = CnMonthlyGoal.query.filter_by(
            cn_id=cn.id, month=month, year=year
        ).first()
        if goal is None:
            missing.append(f"{cn.name} → {month}/{year}")
    return missing


def run_cn_monthly_appraisal(month: int, year: int) -> dict:
    """Run monthly CN apuração for (month, year) with zero realized values.

    Used by tests and internal calls. For the API with real inputs, use
    run_cn_monthly_appraisal_with_inputs().

    Raises MissingGoalsError if any active CN lacks a goal.
    Skips CNs whose appraisal is already LOCKED.
    Replaces non-LOCKED appraisals on re-run.
    """
    missing = validate_cn_goals(month, year)
    if missing:
        raise MissingGoalsError(missing)

    final_ids = {
        row.cn_id
        for row in CnMonthlyAppraisal.query.filter(
            CnMonthlyAppraisal.month == month,
            CnMonthlyAppraisal.year == year,
            CnMonthlyAppraisal.status == AppraisalStatus.LOCKED,
        ).all()
    }

    CnMonthlyAppraisal.query.filter(
        CnMonthlyAppraisal.month == month,
        CnMonthlyAppraisal.year == year,
        CnMonthlyAppraisal.status != AppraisalStatus.LOCKED,
    ).delete(synchronize_session=False)
    db.session.flush()

    active_cns = User.query.filter_by(role=UserRole.CN, active=True).all()
    created = 0

    for cn in active_cns:
        if cn.id in final_ids:
            continue

        goal = CnMonthlyGoal.query.filter_by(
            cn_id=cn.id, month=month, year=year
        ).first()

        nivel = cn.nivel if isinstance(cn.nivel, str) else (cn.nivel.value if cn.nivel else "CN1")
        result = simulate_cn(
            nivel=nivel,
            sao_meta=Decimal(str(goal.sao_target)),
            sao_realizado=Decimal("0"),
            vidas_meta=_vidas_meta_for(cn, goal),
            vidas_realizado=Decimal("0"),
        )

        appraisal = CnMonthlyAppraisal(
            cn_id=cn.id,
            month=month,
            year=year,
            sao_realizado=Decimal("0"),
            vidas_realizado=Decimal("0"),
            pct_sao=Decimal(result["pct_sao"]),
            pct_vidas=Decimal(result["pct_vidas"]),
            score_final=Decimal(result["score_final"]),
            multiplicador=Decimal(result["multiplicador"]),
            commission_amount=Decimal(result["commission_amount"]),
            status=AppraisalStatus.CALCULATING,
        )
        db.session.add(appraisal)
        created += 1

    db.session.flush()
    return {"appraisals_created": created, "month": month, "year": year}


def run_cn_monthly_appraisal_with_inputs(
    month: int, year: int, inputs: list[dict]
) -> dict:
    """Run apuração using provided realized values.

    inputs: [{"cn_id": "<uuid>", "sao_realizado": N, "vidas_realizado": N}, ...]
    Raises MissingGoalsError if any active CN lacks a goal.
    """
    missing = validate_cn_goals(month, year)
    if missing:
        raise MissingGoalsError(missing)

    inputs_by_cn = {item["cn_id"]: item for item in inputs}

    final_ids = {
        row.cn_id
        for row in CnMonthlyAppraisal.query.filter(
            CnMonthlyAppraisal.month == month,
            CnMonthlyAppraisal.year == year,
            CnMonthlyAppraisal.status == AppraisalStatus.LOCKED,
        ).all()
    }

    CnMonthlyAppraisal.query.filter(
        CnMonthlyAppraisal.month == month,
        CnMonthlyAppraisal.year == year,
        CnMonthlyAppraisal.status != AppraisalStatus.LOCKED,
    ).delete(synchronize_session=False)
    db.session.flush()

    active_cns = User.query.filter_by(role=UserRole.CN, active=True).all()
    created = 0

    for cn in active_cns:
        if cn.id in final_ids:
            continue

        goal = CnMonthlyGoal.query.filter_by(
            cn_id=cn.id, month=month, year=year
        ).first()

        cn_input = inputs_by_cn.get(str(cn.id), {})
        sao_realizado = Decimal(str(cn_input.get("sao_realizado", 0)))
        vidas_realizado = Decimal(str(cn_input.get("vidas_realizado", 0)))

        nivel = cn.nivel if isinstance(cn.nivel, str) else (cn.nivel.value if cn.nivel else "CN1")
        result = simulate_cn(
            nivel=nivel,
            sao_meta=Decimal(str(goal.sao_target)),
            sao_realizado=sao_realizado,
            vidas_meta=_vidas_meta_for(cn, goal),
            vidas_realizado=vidas_realizado,
        )

        appraisal = CnMonthlyAppraisal(
            cn_id=cn.id,
            month=month,
            year=year,
            sao_realizado=sao_realizado,
            vidas_realizado=vidas_realizado,
            pct_sao=Decimal(result["pct_sao"]),
            pct_vidas=Decimal(result["pct_vidas"]),
            score_final=Decimal(result["score_final"]),
            multiplicador=Decimal(result["multiplicador"]),
            commission_amount=Decimal(result["commission_amount"]),
            status=AppraisalStatus.CALCULATING,
        )
        db.session.add(appraisal)
        created += 1

    db.session.flush()
    return {"appraisals_created": created, "month": month, "year": year}
