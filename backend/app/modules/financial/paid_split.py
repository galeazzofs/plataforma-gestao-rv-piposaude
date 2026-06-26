"""Split EV-payable paid amounts into Comissao vs Agenciamento.

The paid value is always the apuracao's EV cut (``Commission.total_actual``,
Escala pagavel ao EV). The NF gross rows only decide the *weight* of the
Comissao/Agenciamento split for a policy-month — never the paid value itself
(CONTEXT.md, ADR-0001).
"""
from decimal import Decimal, ROUND_HALF_UP

from app.modules.financial.monthly_engine import (
    classify_revenue_type, COMISSAO, AGENCIAMENTO,
)

_CENTS = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(_CENTS, rounding=ROUND_HALF_UP)


def allocate_paid_split(paid_total, gross_comissao, gross_agenciamento):
    """Split an EV-payable ``paid_total`` by NF gross weights.

    With no gross split on record, the whole amount is treated as Comissao.
    Returns ``(comissao, agenciamento)`` that always sum back to ``paid_total``.
    """
    paid_total = _money(paid_total)
    weight = abs(_money(gross_comissao)) + abs(_money(gross_agenciamento))
    if weight == 0:
        return paid_total, Decimal("0.00")
    comissao = _money(paid_total * (abs(_money(gross_comissao)) / weight))
    return comissao, paid_total - comissao


def _gross_split_by_month(policy):
    """{(month, year): [comissao_gross, agenciamento_gross]} from matched NF."""
    from app.models import FinancialImport

    gross: dict = {}
    rows = FinancialImport.query.filter(
        FinancialImport.policy_id == policy.id,
        FinancialImport.match_status == "MATCHED",
    ).all()
    for nf in rows:
        kind = classify_revenue_type(nf.tipo_receita)
        if kind is None:
            continue
        bucket = gross.setdefault((nf.month, nf.year), [Decimal("0"), Decimal("0")])
        amount = nf.nf_valor_liquido or Decimal("0")
        if kind == COMISSAO:
            bucket[0] += amount
        elif kind == AGENCIAMENTO:
            bucket[1] += amount
    return gross


def policy_apuracao_paid(policy):
    """EV-payable ``(comissao, agenciamento)`` paid across finalized apuracoes.

    Excludes the manual pre-platform baseline (the caller adds that)."""
    gross = _gross_split_by_month(policy)
    comissao = Decimal("0.00")
    agenciamento = Decimal("0.00")
    for c in policy.commissions or []:
        if not c.is_final or c.total_actual is None:
            continue
        gc, ga = gross.get((c.month, c.year), (Decimal("0"), Decimal("0")))
        cc, ca = allocate_paid_split(c.total_actual, gc, ga)
        comissao += cc
        agenciamento += ca
    return comissao, agenciamento
