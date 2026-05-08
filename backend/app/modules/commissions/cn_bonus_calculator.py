"""CN quarterly SAO bonus runner (issue #33).

Bonus = salario_base × multiplier based on the CN's trimestral SAO
attainment. Same régua as the EV bonus, but eligibility kicks in only
above 80%:

  pct_sao_trim < 0.80   → 0    (não elegível)
  pct_sao_trim < 0.95   → 0.5
  pct_sao_trim < 1.25   → 1.0
  pct_sao_trim ≥ 1.25   → 1.5

Pré-condição: os 3 ``CnMonthlyAppraisal`` do trimestre devem estar
``is_final=True``. CNs que não satisfaçam isso são pulados.

Idempotência: bônus não-finais para o (quarter, year) são apagados
antes do cálculo, e os finais são preservados.
"""
from decimal import Decimal

from app.extensions import db
from app.models import (
    CnMonthlyAppraisal,
    CnMonthlyGoal,
    CnQuarterBonus,
    User,
    UserRole,
)


_QUARTER_MONTHS = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}


def _bonus_multiplier(pct_sao_trim: Decimal) -> Decimal:
    if pct_sao_trim < Decimal("0.80"):
        return Decimal("0")
    if pct_sao_trim < Decimal("0.95"):
        return Decimal("0.5")
    if pct_sao_trim < Decimal("1.25"):
        return Decimal("1.0")
    return Decimal("1.5")


def run_cn_quarterly_bonus(quarter: int, year: int) -> dict:
    """Compute and persist trimestral CN bonuses for (quarter, year).

    Returns counts: bonuses_computed, skipped_missing_month,
    skipped_below_eligibility, skipped_no_salary, kept_final.
    """
    if quarter not in _QUARTER_MONTHS:
        raise ValueError(f"quarter must be 1..4, got {quarter}")

    months = _QUARTER_MONTHS[quarter]

    # Wipe non-final rows so the run is idempotent. is_final=True rows
    # remain untouched.
    CnQuarterBonus.query.filter_by(
        quarter=quarter, year=year, is_final=False,
    ).delete(synchronize_session=False)

    final_cn_ids = {
        b.cn_id
        for b in CnQuarterBonus.query.filter_by(
            quarter=quarter, year=year, is_final=True,
        ).all()
    }

    cns = User.query.filter_by(role=UserRole.CN, active=True).all()

    bonuses_computed = 0
    skipped_missing_month = 0
    skipped_below_eligibility = 0
    skipped_no_salary = 0
    kept_final = 0

    for cn in cns:
        if cn.id in final_cn_ids:
            kept_final += 1
            continue

        appraisals = CnMonthlyAppraisal.query.filter(
            CnMonthlyAppraisal.cn_id == cn.id,
            CnMonthlyAppraisal.year == year,
            CnMonthlyAppraisal.month.in_(months),
        ).all()

        if len(appraisals) != 3 or not all(a.is_final for a in appraisals):
            skipped_missing_month += 1
            continue

        goals = CnMonthlyGoal.query.filter(
            CnMonthlyGoal.cn_id == cn.id,
            CnMonthlyGoal.year == year,
            CnMonthlyGoal.month.in_(months),
        ).all()
        if len(goals) != 3:
            skipped_missing_month += 1
            continue

        sao_realizado = sum(
            (Decimal(str(a.sao_realizado)) for a in appraisals),
            Decimal("0"),
        )
        sao_meta = sum(
            (Decimal(str(g.sao_target)) for g in goals),
            Decimal("0"),
        )
        pct = (sao_realizado / sao_meta) if sao_meta > 0 else Decimal("0")
        mult = _bonus_multiplier(pct)

        if mult == 0:
            skipped_below_eligibility += 1

        salario = (
            Decimal(str(cn.salario_base)) if cn.salario_base is not None else None
        )
        if salario is None:
            skipped_no_salary += 1

        bonus = (
            (salario * mult).quantize(Decimal("0.01")) if salario is not None
            else Decimal("0.00")
        )

        db.session.add(CnQuarterBonus(
            cn_id=cn.id,
            quarter=quarter,
            year=year,
            sao_trim_realizado=sao_realizado.quantize(Decimal("0.01")),
            sao_trim_meta=sao_meta.quantize(Decimal("0.01")),
            pct_sao_trim=pct.quantize(Decimal("0.0001")),
            multiplicador=mult,
            bonus_amount=bonus,
            salario_base_snapshot=salario,
            is_final=False,
        ))
        bonuses_computed += 1

    db.session.flush()

    return {
        "quarter": quarter,
        "year": year,
        "bonuses_computed": bonuses_computed,
        "skipped_missing_month": skipped_missing_month,
        "skipped_below_eligibility": skipped_below_eligibility,
        "skipped_no_salary": skipped_no_salary,
        "kept_final": kept_final,
    }
