"""Shared policy clock helpers for Comissao month counting."""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import tuple_

from app.extensions import db
from app.models import Appraisal, AppraisalStatus, Commission, FinancialImport
from app.modules.financial.monthly_engine import COMISSAO, classify_revenue_type


def period_before(left: tuple[int, int], right: tuple[int, int]) -> bool:
    """Return whether (month, year) `left` is before (month, year) `right`."""
    left_month, left_year = left
    right_month, right_year = right
    return (left_year, left_month) < (right_year, right_month)


def locked_period_pairs(*, before: tuple[int, int] | None = None) -> set[tuple[int, int]]:
    """Locked Apuracao periods that officially count toward the policy clock."""
    appraisal_pairs = {
        (m, y) for m, y in db.session.query(Appraisal.month, Appraisal.year)
        .filter(Appraisal.status == AppraisalStatus.LOCKED)
        .all()
    }
    commission_pairs = {
        (m, y) for m, y in db.session.query(Commission.month, Commission.year)
        .filter(Commission.is_final.is_(True))
        .all()
    }
    pairs = appraisal_pairs | commission_pairs
    if before is None:
        return pairs
    return {pair for pair in pairs if period_before(pair, before)}


def positive_locked_comissao_month_counts(
    policy_ids: set | None = None,
    *,
    before: tuple[int, int] | None = None,
) -> dict:
    """Count positive locked Mes de comissao pago values per policy."""
    if policy_ids is not None and not policy_ids:
        return {}

    pairs = locked_period_pairs(before=before)
    if not pairs:
        return {}

    query = db.session.query(
        FinancialImport.policy_id,
        FinancialImport.nf_mes_recebimento,
        FinancialImport.tipo_receita,
        db.func.coalesce(db.func.sum(FinancialImport.nf_valor_liquido), 0),
    ).filter(
        FinancialImport.match_status == "MATCHED",
        FinancialImport.policy_id.isnot(None),
        tuple_(FinancialImport.month, FinancialImport.year).in_(pairs),
    )
    if policy_ids is not None:
        query = query.filter(FinancialImport.policy_id.in_(policy_ids))

    rows = query.group_by(
        FinancialImport.policy_id,
        FinancialImport.nf_mes_recebimento,
        FinancialImport.tipo_receita,
    ).all()

    monthly = defaultdict(lambda: defaultdict(Decimal))
    for policy_id, ym, tipo, total in rows:
        if classify_revenue_type(tipo) == COMISSAO:
            monthly[policy_id][ym] += total or Decimal("0")

    return {
        policy_id: sum(1 for total in months.values() if total > 0)
        for policy_id, months in monthly.items()
    }
