"""Read model for Finance monthly payable obligations."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.extensions import db
from app.models import (
    Appraisal,
    AppraisalStatus,
    CommissionStatus,
    FinancialImport,
    Policy,
)
from app.modules.financial.monthly_engine import (
    A_APURAR,
    PROJETADO,
    REALIZADO,
    FinancialRow,
    PolicyFinancialState,
    build_monthly_financial_engine,
    classify_revenue_type,
)


def _payment_start(policy: Policy) -> date | None:
    return (
        policy.first_payment_real
        or policy.first_payment_prev
        or policy.deploy_date
        or policy.closed_date
    )


def _policy_projection_start_month(policy: Policy, fallback: date) -> str:
    start = _payment_start(policy) or fallback
    months_paid = max(0, min(policy.installments_paid or 0, 12))
    scheduled = start + relativedelta(months=months_paid)
    fallback_ym = fallback.strftime("%Y-%m")
    projected_ym = scheduled.strftime("%Y-%m")
    return max(projected_ym, fallback_ym)


def _locked_appraisal_pairs() -> set[tuple[int, int]]:
    return {
        (m, y)
        for m, y in db.session.query(Appraisal.month, Appraisal.year)
        .filter(Appraisal.status == AppraisalStatus.LOCKED)
        .all()
    }


def _finance_policy_states(
    active_policies,
    fallback: date,
) -> list[PolicyFinancialState]:
    states = []
    for policy in active_policies:
        states.append(PolicyFinancialState(
            policy_id=str(policy.id),
            commission_potential=policy.commission_potential or Decimal("0"),
            projection_start_month=_policy_projection_start_month(policy, fallback),
            initial_installments_paid=policy.initial_installments_paid or 0,
            commission_paid_legacy=policy.commission_paid_legacy or Decimal("0"),
            commission_status=(
                policy.commission_status.value
                if hasattr(policy.commission_status, "value")
                else policy.commission_status
            ),
        ))
    return states


def _finance_rows_for_policies(
    policy_ids: set[str],
    locked_pairs: set[tuple[int, int]],
) -> list[FinancialRow]:
    if not policy_ids:
        return []
    rows = (
        FinancialImport.query.filter(
            FinancialImport.match_status == "MATCHED",
            FinancialImport.policy_id.isnot(None),
            FinancialImport.policy_id.in_(policy_ids),
        )
        .all()
    )
    result = []
    for row in rows:
        if classify_revenue_type(row.tipo_receita) is None:
            continue
        result.append(FinancialRow(
            policy_id=str(row.policy_id),
            month=row.nf_mes_recebimento,
            amount=row.nf_valor_liquido,
            revenue_type=row.tipo_receita,
            is_locked=(row.month, row.year) in locked_pairs,
        ))
    return result


def _locked_realized_by_month(
    locked_pairs: set[tuple[int, int]],
) -> dict[str, Decimal]:
    if not locked_pairs:
        return {}
    rows = (
        FinancialImport.query.filter(
            FinancialImport.match_status == "MATCHED",
            FinancialImport.policy_id.isnot(None),
        )
        .all()
    )
    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in rows:
        if (row.month, row.year) not in locked_pairs:
            continue
        if classify_revenue_type(row.tipo_receita) is None:
            continue
        by_month[row.nf_mes_recebimento] += row.nf_valor_liquido or Decimal("0")
    return dict(by_month)


def build_monthly_finance_view(today: date):
    """Return monthly Finance engine output plus totals grouped by month."""
    active_policies = Policy.query.filter(
        Policy.commission_status.notin_(
            [CommissionStatus.SETTLED, CommissionStatus.CANCELLED]
        ),
        Policy.installments_paid < 12,
    ).all()
    locked_pairs = _locked_appraisal_pairs()
    policy_ids = {str(policy.id) for policy in active_policies}
    engine = build_monthly_financial_engine(
        _finance_policy_states(active_policies, today),
        _finance_rows_for_policies(policy_ids, locked_pairs),
    )

    entries_by_month: dict[str, dict[str, Decimal | set]] = defaultdict(
        lambda: {
            REALIZADO: Decimal("0"),
            A_APURAR: Decimal("0"),
            PROJETADO: Decimal("0"),
            "apolices": set(),
        }
    )
    for month, amount in _locked_realized_by_month(locked_pairs).items():
        entries_by_month[month][REALIZADO] += amount
    for entry in engine.entries:
        if entry.state == REALIZADO:
            continue
        entries_by_month[entry.month][entry.state] += entry.amount
        entries_by_month[entry.month]["apolices"].add(entry.policy_id)

    return engine, entries_by_month
