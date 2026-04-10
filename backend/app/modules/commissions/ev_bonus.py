"""EV quarterly MRR bonus runner.

Bonus = salario_base × multiplier based on EvQuarterAchievement.achievement_pct.

Multiplier table (spec §2.2):
  < 0.80  → 0x
  < 0.95  → 0.5x
  < 1.25  → 1.0x
  >= 1.25 → 1.5x
"""
from decimal import Decimal

from app.extensions import db
from app.models import EvQuarterAchievement


def _mrr_multiplier(achievement_pct: Decimal) -> Decimal:
    if achievement_pct < Decimal("0.80"):
        return Decimal("0")
    if achievement_pct < Decimal("0.95"):
        return Decimal("0.5")
    if achievement_pct < Decimal("1.25"):
        return Decimal("1.0")
    return Decimal("1.5")


def run_ev_quarterly_bonus(quarter: int, year: int) -> dict:
    """Compute and persist EV MRR bonus for all achievements in (quarter, year).

    Skips achievements that are already is_final=True.
    Skips EVs with no salario_base set.
    """
    achievements = EvQuarterAchievement.query.filter_by(
        quarter=quarter, year=year
    ).all()

    computed = 0
    skipped_final = 0
    skipped_no_salary = 0

    for ach in achievements:
        if ach.is_final:
            skipped_final += 1
            continue

        ev = ach.ev
        if ev is None or ev.salario_base is None:
            skipped_no_salary += 1
            ach.bonus_amount = Decimal("0.00")
            ach.salario_base_snapshot = None
            continue

        salario = Decimal(str(ev.salario_base))
        mult = _mrr_multiplier(Decimal(str(ach.achievement_pct or 0)))
        ach.bonus_amount = (salario * mult).quantize(Decimal("0.01"))
        ach.salario_base_snapshot = salario
        computed += 1

    db.session.flush()
    return {
        "quarter": quarter,
        "year": year,
        "bonuses_computed": computed,
        "skipped_final": skipped_final,
        "skipped_no_salary": skipped_no_salary,
    }
