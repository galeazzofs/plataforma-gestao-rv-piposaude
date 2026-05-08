"""LIDER_VENDAS quarterly leadership bonus runner.

Spec §2.3:
  meta_mrr  = 90% × SUM(Goal.mrr_target for all EVs in lider de vendas's team, quarter, year)
  pct_mrr   = realizado_mrr / meta_mrr
  pct_sql   = realizado_sql / meta_sql
  mult      = MATRIZ_LIDERANCA[mrr_faixa][sql_faixa]
  bonus     = salario_base × mult
"""
from decimal import Decimal

from app.extensions import db
from app.models import (
    AppraisalStatus, EvQuarterAchievement, Goal, LiderVendasQuarterAppraisal,
    Team, User, UserRole,
)

# Matrix rows = MRR faixas, columns = SQL faixas
# MRR faixas: [< 60%, 60-79.9%, 80-94.9%, 95-109.9%, >= 110%]
# SQL faixas: [< 80%, 80-94.9%, 95-109.9%, >= 110%]
_MATRIZ = [
    [Decimal("0"),   Decimal("0"),    Decimal("0"),    Decimal("0")],     # MRR < 60%
    [Decimal("0.5"), Decimal("0.75"), Decimal("1.0"),  Decimal("1.25")],  # MRR 60–79.9%
    [Decimal("1.0"), Decimal("1.5"),  Decimal("2.0"),  Decimal("2.25")],  # MRR 80–94.9%
    [Decimal("1.5"), Decimal("2.0"),  Decimal("3.0"),  Decimal("3.25")],  # MRR 95–109.9%
    [Decimal("2.0"), Decimal("2.75"), Decimal("3.5"),  Decimal("4.0")],   # MRR >= 110%
]

_MRR_THRESHOLDS = [Decimal("0.60"), Decimal("0.80"), Decimal("0.95"), Decimal("1.10")]
_SQL_THRESHOLDS = [Decimal("0.80"), Decimal("0.95"), Decimal("1.10")]


def _row(pct: Decimal, thresholds: list) -> int:
    for i, t in enumerate(thresholds):
        if pct < t:
            return i
    return len(thresholds)


def _lideranca_multiplier(pct_mrr: Decimal, pct_sql: Decimal) -> Decimal:
    return _MATRIZ[_row(pct_mrr, _MRR_THRESHOLDS)][_row(pct_sql, _SQL_THRESHOLDS)]


def _compute_realizado_mrr(lider: User, quarter: int, year: int) -> Decimal:
    """Σ EvQuarterAchievement.total_mrr for the EVs in the líder's team."""
    team = Team.query.filter_by(leader_id=lider.id).first()
    if team is None:
        return Decimal("0.00")

    ev_ids = [
        u.id for u in User.query.filter_by(
            team_id=team.id, role=UserRole.EV, active=True,
        ).all()
    ]
    if not ev_ids:
        return Decimal("0.00")

    achs = EvQuarterAchievement.query.filter(
        EvQuarterAchievement.ev_id.in_(ev_ids),
        EvQuarterAchievement.quarter == quarter,
        EvQuarterAchievement.year == year,
    ).all()
    total = sum(
        (Decimal(str(a.total_mrr)) for a in achs if a.total_mrr is not None),
        Decimal("0"),
    )
    return total.quantize(Decimal("0.01"))


def get_leadership_preview(quarter: int, year: int) -> list:
    """Return list of LIDER_VENDAS users with auto-computed meta_mrr and
    realizado_mrr_auto for (quarter, year). The realizado is editable in
    the UI but defaults to Σ EvQuarterAchievement.total_mrr of the team.
    """
    lideres = User.query.filter_by(role=UserRole.LIDER_VENDAS, active=True).all()
    result = []
    for lider in lideres:
        meta_mrr = _compute_meta_mrr(lider, quarter, year)
        realizado_auto = _compute_realizado_mrr(lider, quarter, year)
        result.append({
            "lider_vendas_id": str(lider.id),
            "lider_vendas_name": lider.name,
            "meta_mrr": str(meta_mrr),
            "realizado_mrr_auto": str(realizado_auto),
        })
    return result


def _compute_meta_mrr(lider: User, quarter: int, year: int) -> Decimal:
    """90% × SUM(Goal.mrr_target for EVs in lider de vendas's team)."""
    team = Team.query.filter_by(leader_id=lider.id).first()
    if team is None:
        return Decimal("0")

    ev_ids = [
        u.id for u in User.query.filter_by(
            team_id=team.id, role=UserRole.EV, active=True
        ).all()
    ]
    if not ev_ids:
        return Decimal("0")

    goals = Goal.query.filter(
        Goal.ev_id.in_(ev_ids),
        Goal.quarter == quarter,
        Goal.year == year,
    ).all()
    total = sum((Decimal(str(g.mrr_target)) for g in goals), Decimal("0"))

    return (total * Decimal("0.90")).quantize(Decimal("0.01"))


def run_leadership_appraisal(
    quarter: int, year: int, inputs: list
) -> dict:
    """Compute and persist LIDER_VENDAS bonus.

    inputs: [{lider_vendas_id, meta_sql, realizado_mrr, realizado_sql}, ...]
    Skips lideres whose appraisal is already LOCKED for this quarter.
    """
    final_ids = {
        str(row.lider_vendas_id)
        for row in LiderVendasQuarterAppraisal.query.filter(
            LiderVendasQuarterAppraisal.quarter == quarter,
            LiderVendasQuarterAppraisal.year == year,
            LiderVendasQuarterAppraisal.status == AppraisalStatus.LOCKED,
        ).all()
    }

    created = 0
    for item in inputs:
        lider_vendas_id = item["lider_vendas_id"]
        if lider_vendas_id in final_ids:
            continue

        lider = db.session.get(User, lider_vendas_id)
        if lider is None or lider.salario_base is None:
            continue

        meta_mrr = _compute_meta_mrr(lider, quarter, year)
        meta_sql = int(item["meta_sql"])
        realizado_mrr = Decimal(str(item["realizado_mrr"]))
        realizado_sql = int(item["realizado_sql"])

        pct_mrr = (realizado_mrr / meta_mrr) if meta_mrr > 0 else Decimal("0")
        pct_sql = (Decimal(realizado_sql) / Decimal(meta_sql)) if meta_sql > 0 else Decimal("0")
        mult = _lideranca_multiplier(pct_mrr, pct_sql)
        bonus = (Decimal(str(lider.salario_base)) * mult).quantize(Decimal("0.01"))

        # Upsert: pick the existing non-LOCKED row if any, else create.
        appraisal = LiderVendasQuarterAppraisal.query.filter(
            LiderVendasQuarterAppraisal.lider_vendas_id == lider_vendas_id,
            LiderVendasQuarterAppraisal.quarter == quarter,
            LiderVendasQuarterAppraisal.year == year,
            LiderVendasQuarterAppraisal.status != AppraisalStatus.LOCKED,
        ).first()
        if appraisal is None:
            appraisal = LiderVendasQuarterAppraisal(
                lider_vendas_id=lider_vendas_id, quarter=quarter, year=year,
                status=AppraisalStatus.CALCULATING,
            )
            db.session.add(appraisal)

        appraisal.meta_mrr = meta_mrr
        appraisal.meta_sql = meta_sql
        appraisal.realizado_mrr = realizado_mrr
        appraisal.realizado_sql = realizado_sql
        appraisal.pct_mrr = pct_mrr.quantize(Decimal("0.0001"))
        appraisal.pct_sql = pct_sql.quantize(Decimal("0.0001"))
        appraisal.multiplicador = mult
        appraisal.bonus_amount = bonus
        if appraisal.status == AppraisalStatus.LOCKED:
            # Defensive — should not happen because of filter above.
            continue
        if appraisal.status is None:
            appraisal.status = AppraisalStatus.CALCULATING
        created += 1

    db.session.flush()
    return {"quarter": quarter, "year": year, "appraisals_created": created}
