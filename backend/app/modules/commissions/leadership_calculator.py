"""GERENTE quarterly leadership bonus runner.

Spec §2.3:
  meta_mrr  = 90% × SUM(Goal.mrr_target for all EVs in gerente's team, quarter, year)
  pct_mrr   = realizado_mrr / meta_mrr
  pct_sql   = realizado_sql / meta_sql
  mult      = MATRIZ_LIDERANCA[mrr_faixa][sql_faixa]
  bonus     = salario_base × mult
"""
from decimal import Decimal

from app.extensions import db
from app.models import User, UserRole, Goal, Team, GerenteQuarterAppraisal

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


def get_leadership_preview(quarter: int, year: int) -> list:
    """Return list of GERENTEs with auto-computed meta_mrr for (quarter, year)."""
    gerentes = User.query.filter_by(role=UserRole.GERENTE, active=True).all()
    result = []
    for gerente in gerentes:
        meta_mrr = _compute_meta_mrr(gerente, quarter, year)
        result.append({
            "gerente_id": str(gerente.id),
            "gerente_name": gerente.name,
            "meta_mrr": str(meta_mrr),
        })
    return result


def _compute_meta_mrr(gerente: User, quarter: int, year: int) -> Decimal:
    """90% × SUM(Goal.mrr_target for EVs in gerente's team)."""
    team = Team.query.filter_by(leader_id=gerente.id).first()
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
    """Compute and persist GERENTE bonus.

    inputs: [{gerente_id, meta_sql, realizado_mrr, realizado_sql}, ...]
    Skips GERENTEs already is_final=True for this quarter.
    """
    final_ids = {
        str(row.gerente_id)
        for row in GerenteQuarterAppraisal.query.filter_by(
            quarter=quarter, year=year, is_final=True
        ).all()
    }

    created = 0
    for item in inputs:
        gerente_id = item["gerente_id"]
        if gerente_id in final_ids:  # gerente_id is already str from item["gerente_id"]
            continue

        gerente = db.session.get(User, gerente_id)
        if gerente is None or gerente.salario_base is None:
            continue

        meta_mrr = _compute_meta_mrr(gerente, quarter, year)
        meta_sql = int(item["meta_sql"])
        realizado_mrr = Decimal(str(item["realizado_mrr"]))
        realizado_sql = int(item["realizado_sql"])

        pct_mrr = (realizado_mrr / meta_mrr) if meta_mrr > 0 else Decimal("0")
        pct_sql = (Decimal(realizado_sql) / Decimal(meta_sql)) if meta_sql > 0 else Decimal("0")
        mult = _lideranca_multiplier(pct_mrr, pct_sql)
        bonus = (Decimal(str(gerente.salario_base)) * mult).quantize(Decimal("0.01"))

        # Upsert
        appraisal = GerenteQuarterAppraisal.query.filter_by(
            gerente_id=gerente_id, quarter=quarter, year=year, is_final=False
        ).first()
        if appraisal is None:
            appraisal = GerenteQuarterAppraisal(
                gerente_id=gerente_id, quarter=quarter, year=year
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
        appraisal.is_final = False
        created += 1

    db.session.flush()
    return {"quarter": quarter, "year": year, "appraisals_created": created}
