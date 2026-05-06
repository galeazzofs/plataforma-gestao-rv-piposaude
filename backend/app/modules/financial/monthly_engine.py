"""Pure monthly finance engine for payable commission obligations.

This module has no database dependency. Callers pass policy snapshots and
matched financial rows; the engine returns monthly Realizado / A apurar /
Projetado entries plus totals that Finance can later expose.
"""
from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


COMISSAO = "COMISSAO"
AGENCIAMENTO = "AGENCIAMENTO"

REALIZADO = "REALIZADO"
A_APURAR = "A_APURAR"
PROJETADO = "PROJETADO"

SETTLED = "SETTLED"
CANCELLED = "CANCELLED"

_CENTS = Decimal("0.01")


def _money(value: Decimal | int | str | float | None) -> Decimal:
    return Decimal(str(value or "0")).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def classify_revenue_type(tipo_receita: str | None) -> str | None:
    """Return canonical commissionable revenue type or None."""
    normalized = _strip_accents((tipo_receita or "").strip().lower())
    if "comiss" in normalized:
        return COMISSAO
    if "agenc" in normalized:
        return AGENCIAMENTO
    return None


def add_months(ym: str, months: int) -> str:
    year, month = (int(part) for part in ym.split("-"))
    index = (year * 12) + (month - 1) + months
    return f"{index // 12}-{(index % 12) + 1:02d}"


@dataclass(frozen=True)
class FinancialRow:
    policy_id: str
    month: str
    amount: Decimal | int | str | float
    revenue_type: str | None
    is_locked: bool = False


@dataclass(frozen=True)
class PolicyFinancialState:
    policy_id: str
    commission_potential: Decimal | int | str | float
    projection_start_month: str
    initial_installments_paid: int = 0
    commission_paid_legacy: Decimal | int | str | float = Decimal("0")
    commission_status: str | None = None


@dataclass(frozen=True)
class MonthlyRevenue:
    comissao: Decimal = Decimal("0")
    agenciamento: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return _money(self.comissao + self.agenciamento)

    @property
    def reserves_commission_month(self) -> bool:
        return self.comissao > 0


@dataclass(frozen=True)
class MonthlyFinancialEntry:
    policy_id: str
    month: str
    state: str
    amount: Decimal
    comissao: Decimal = Decimal("0")
    agenciamento: Decimal = Decimal("0")
    reserves_commission_month: bool = False


@dataclass(frozen=True)
class PolicyMonthlySummary:
    policy_id: str
    locked_commission_months: int
    pending_reserved_months: int
    projected_months: int
    clock_months_with_pending: int
    monthly_projected_comissao: Decimal
    is_fully_paid_with_pending: bool


@dataclass(frozen=True)
class MonthlyFinancialResult:
    entries: tuple[MonthlyFinancialEntry, ...]
    payable_potential: Decimal
    realized_total: Decimal
    pending_total: Decimal
    projected_total: Decimal
    policies: dict[str, PolicyMonthlySummary]


def group_monthly_revenue(rows: Iterable[FinancialRow]) -> dict[str, dict[str, MonthlyRevenue]]:
    """Group commissionable rows by policy/month, ignoring non-commissionable types."""
    grouped = defaultdict(lambda: defaultdict(lambda: {"comissao": Decimal("0"), "agenciamento": Decimal("0")}))

    for row in rows:
        kind = classify_revenue_type(row.revenue_type)
        if kind is None:
            continue
        amount = _money(row.amount)
        bucket = grouped[row.policy_id][row.month]
        if kind == COMISSAO:
            bucket["comissao"] += amount
        elif kind == AGENCIAMENTO:
            bucket["agenciamento"] += amount

    return {
        policy_id: {
            month: MonthlyRevenue(
                comissao=_money(values["comissao"]),
                agenciamento=_money(values["agenciamento"]),
            )
            for month, values in months.items()
        }
        for policy_id, months in grouped.items()
    }


def split_locked_and_pending(
    rows: Iterable[FinancialRow],
) -> tuple[dict[str, dict[str, MonthlyRevenue]], dict[str, dict[str, MonthlyRevenue]]]:
    locked_rows = []
    pending_rows = []
    for row in rows:
        if row.is_locked:
            locked_rows.append(row)
        else:
            pending_rows.append(row)
    return group_monthly_revenue(locked_rows), group_monthly_revenue(pending_rows)


def positive_commission_month_count(months: dict[str, MonthlyRevenue]) -> int:
    return sum(1 for revenue in months.values() if revenue.comissao > 0)


def compute_real_weighted_average(
    *,
    commission_paid_legacy: Decimal | int | str | float | None,
    initial_installments_paid: int | None,
    locked_months: dict[str, MonthlyRevenue],
    commission_potential: Decimal | int | str | float | None,
) -> Decimal:
    """Weighted monthly Comissao.

    Real signal wins: legacy Comissao + locked platform Comissao, divided by
    legacy months + positive locked Comissao months. Contractual monthly
    potential is fallback only. No cap is applied.
    """
    legacy_months = max(0, int(initial_installments_paid or 0))
    legacy_paid = _money(commission_paid_legacy)
    locked_commissao = _money(sum((m.comissao for m in locked_months.values()), Decimal("0")))
    locked_positive_months = positive_commission_month_count(locked_months)
    real_months = legacy_months + locked_positive_months

    if real_months > 0:
        return _money((legacy_paid + locked_commissao) / Decimal(real_months))

    potential = _money(commission_potential)
    if potential <= 0:
        return Decimal("0.00")
    return _money(potential / Decimal("12"))


def build_monthly_financial_engine(
    policies: Iterable[PolicyFinancialState],
    rows: Iterable[FinancialRow],
) -> MonthlyFinancialResult:
    """Build monthly payable obligation entries.

    LOCKED rows become Realizado and do not enter payable_potential.
    Pending matched rows become A apurar and replace projection for that
    policy-month. Pending positive net Comissao reserves one clock month but
    does not recalibrate future projection average.
    """
    locked_by_policy, pending_by_policy = split_locked_and_pending(rows)
    entries: list[MonthlyFinancialEntry] = []
    summaries: dict[str, PolicyMonthlySummary] = {}

    realized_total = Decimal("0")
    pending_total = Decimal("0")
    projected_total = Decimal("0")

    for policy in policies:
        if policy.commission_status in {SETTLED, CANCELLED}:
            summaries[policy.policy_id] = PolicyMonthlySummary(
                policy_id=policy.policy_id,
                locked_commission_months=0,
                pending_reserved_months=0,
                projected_months=0,
                clock_months_with_pending=min(12, int(policy.initial_installments_paid or 0)),
                monthly_projected_comissao=Decimal("0.00"),
                is_fully_paid_with_pending=True,
            )
            continue

        locked_months = locked_by_policy.get(policy.policy_id, {})
        pending_months = pending_by_policy.get(policy.policy_id, {})

        for month in sorted(locked_months):
            revenue = locked_months[month]
            if revenue.total == 0:
                continue
            entries.append(MonthlyFinancialEntry(
                policy_id=policy.policy_id,
                month=month,
                state=REALIZADO,
                amount=revenue.total,
                comissao=revenue.comissao,
                agenciamento=revenue.agenciamento,
                reserves_commission_month=revenue.reserves_commission_month,
            ))
            realized_total += revenue.total

        monthly_projected = compute_real_weighted_average(
            commission_paid_legacy=policy.commission_paid_legacy,
            initial_installments_paid=policy.initial_installments_paid,
            locked_months=locked_months,
            commission_potential=policy.commission_potential,
        )

        locked_count = positive_commission_month_count(locked_months)
        clock_months = min(12, max(0, int(policy.initial_installments_paid or 0)) + locked_count)

        pending_reserved = 0
        for month in sorted(pending_months):
            if clock_months >= 12:
                break
            revenue = pending_months[month]
            if revenue.total != 0:
                entries.append(MonthlyFinancialEntry(
                    policy_id=policy.policy_id,
                    month=month,
                    state=A_APURAR,
                    amount=revenue.total,
                    comissao=revenue.comissao,
                    agenciamento=revenue.agenciamento,
                    reserves_commission_month=revenue.reserves_commission_month,
                ))
                pending_total += revenue.total
            if revenue.reserves_commission_month:
                clock_months += 1
                pending_reserved += 1

        pending_month_keys = set(pending_months.keys())
        occupied_months = set(locked_months.keys()) | pending_month_keys
        projected_count = 0
        remaining = max(0, 12 - clock_months)
        cursor = policy.projection_start_month
        while remaining > 0 and monthly_projected > 0:
            if cursor not in occupied_months:
                entries.append(MonthlyFinancialEntry(
                    policy_id=policy.policy_id,
                    month=cursor,
                    state=PROJETADO,
                    amount=monthly_projected,
                    comissao=monthly_projected,
                    agenciamento=Decimal("0.00"),
                    reserves_commission_month=True,
                ))
                projected_total += monthly_projected
                projected_count += 1
                remaining -= 1
            cursor = add_months(cursor, 1)

        summaries[policy.policy_id] = PolicyMonthlySummary(
            policy_id=policy.policy_id,
            locked_commission_months=locked_count,
            pending_reserved_months=pending_reserved,
            projected_months=projected_count,
            clock_months_with_pending=clock_months,
            monthly_projected_comissao=monthly_projected,
            is_fully_paid_with_pending=clock_months >= 12,
        )

    entries.sort(key=lambda entry: (entry.month, entry.policy_id, entry.state))
    payable = _money(pending_total + projected_total)
    return MonthlyFinancialResult(
        entries=tuple(entries),
        payable_potential=payable,
        realized_total=_money(realized_total),
        pending_total=_money(pending_total),
        projected_total=_money(projected_total),
        policies=summaries,
    )
