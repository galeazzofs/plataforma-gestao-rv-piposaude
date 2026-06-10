from decimal import Decimal

from app.modules.financial.monthly_engine import (
    AGENCIAMENTO,
    A_APURAR,
    CANCELLED,
    COMISSAO,
    PROJETADO,
    REALIZADO,
    SETTLED,
    FinancialRow,
    PolicyFinancialState,
    build_monthly_financial_engine,
    classify_revenue_type,
    group_monthly_revenue,
)


def _policy(**kwargs):
    base = {
        "policy_id": "policy-1",
        "commission_potential": Decimal("1200.00"),
        "projection_start_month": "2026-04",
    }
    base.update(kwargs)
    return PolicyFinancialState(**base)


def test_classifies_only_comissao_and_agenciamento_as_commissionable():
    assert classify_revenue_type("Comissão") == COMISSAO
    assert classify_revenue_type("Agenciamento") == AGENCIAMENTO
    assert classify_revenue_type("Fee por Vida") is None
    assert classify_revenue_type("Premiação") is None
    assert classify_revenue_type(None) is None


def test_groups_monthly_net_comissao_and_ignores_non_commissionable_rows():
    grouped = group_monthly_revenue([
        FinancialRow("policy-1", "2026-04", "100.00", "Comissão"),
        FinancialRow("policy-1", "2026-04", "-120.00", "Comissão"),
        FinancialRow("policy-1", "2026-04", "35.00", "Agenciamento"),
        FinancialRow("policy-1", "2026-04", "999.00", "Patrocínio"),
    ])

    month = grouped["policy-1"]["2026-04"]
    assert month.comissao == Decimal("-20.00")
    assert month.agenciamento == Decimal("35.00")
    assert month.total == Decimal("15.00")
    assert month.reserves_commission_month is False


def test_projected_monthly_is_contractual_potential_even_with_real_history():
    # Regression for the R$3.69M dashboard bug (2026-06-10): locked NF rows
    # carry gross operadora revenue, a different money scale than the EV
    # payable. They must never recalibrate the projection — the payable
    # monthly is always Comissao potencial da apolice / 12.
    result = build_monthly_financial_engine(
        policies=[_policy(initial_installments_paid=1)],
        rows=[
            FinancialRow("policy-1", "2026-03", "35000.00", "Comissão", is_locked=True),
        ],
    )

    assert result.policies["policy-1"].monthly_projected_comissao == Decimal("100.00")
    # clock = 1 legacy + 1 locked → 10 remaining months × 100.00
    assert result.projected_total == Decimal("1000.00")
    assert result.payable_potential == Decimal("1000.00")


def test_pending_month_is_valued_at_contractual_monthly_and_reserves_clock():
    result = build_monthly_financial_engine(
        policies=[_policy()],
        rows=[
            FinancialRow("policy-1", "2026-04", "80.00", "Comissão"),
        ],
    )

    april_entries = [
        entry for entry in result.entries
        if entry.policy_id == "policy-1" and entry.month == "2026-04"
    ]

    assert [(entry.state, entry.amount) for entry in april_entries] == [
        (A_APURAR, Decimal("100.00"))
    ]
    assert result.policies["policy-1"].pending_reserved_months == 1
    assert result.policies["policy-1"].monthly_projected_comissao == Decimal("100.00")
    assert result.projected_total == Decimal("1100.00")
    assert result.payable_potential == Decimal("1200.00")


def test_agenciamento_only_pending_month_is_not_payable_and_does_not_reserve_clock():
    result = build_monthly_financial_engine(
        policies=[_policy()],
        rows=[
            FinancialRow("policy-1", "2026-04", "75.00", "Agenciamento"),
        ],
    )

    april_entries = [
        entry for entry in result.entries
        if entry.policy_id == "policy-1" and entry.month == "2026-04"
    ]

    assert april_entries == []
    assert result.policies["policy-1"].pending_reserved_months == 0
    assert result.policies["policy-1"].clock_months_with_pending == 0
    assert result.pending_total == Decimal("0.00")
    assert result.projected_total == Decimal("1200.00")
    assert result.payable_potential == Decimal("1200.00")


def test_pending_comissao_plus_agenciamento_can_complete_twelfth_month():
    result = build_monthly_financial_engine(
        policies=[
            _policy(initial_installments_paid=10)
        ],
        rows=[
            FinancialRow("policy-1", "2026-04", "200.00", "Comissão", is_locked=True),
            FinancialRow("policy-1", "2026-05", "300.00", "Comissão"),
            FinancialRow("policy-1", "2026-05", "40.00", "Agenciamento"),
        ],
    )

    may_entries = [
        entry for entry in result.entries
        if entry.policy_id == "policy-1" and entry.month == "2026-05"
    ]

    assert [(entry.state, entry.amount, entry.comissao, entry.agenciamento) for entry in may_entries] == [
        (A_APURAR, Decimal("100.00"), Decimal("100.00"), Decimal("0.00"))
    ]
    assert result.realized_total == Decimal("200.00")
    assert result.pending_total == Decimal("100.00")
    assert result.projected_total == Decimal("0.00")
    assert result.policies["policy-1"].is_fully_paid_with_pending is True


def test_locked_rows_are_realized_and_do_not_enter_payable_potential():
    result = build_monthly_financial_engine(
        policies=[_policy(initial_installments_paid=1)],
        rows=[
            FinancialRow("policy-1", "2026-03", "250.00", "Comissão", is_locked=True),
            FinancialRow("policy-1", "2026-03", "60.00", "Agenciamento", is_locked=True),
        ],
    )

    realized = [entry for entry in result.entries if entry.state == REALIZADO]

    assert len(realized) == 1
    assert realized[0].amount == Decimal("310.00")
    assert result.realized_total == Decimal("310.00")
    # clock = 1 legacy + 1 locked → 10 remaining months × 100.00
    assert result.payable_potential == result.projected_total
    assert result.payable_potential == Decimal("1000.00")


def test_settled_and_cancelled_policies_generate_no_entries():
    result = build_monthly_financial_engine(
        policies=[
            _policy(policy_id="settled", commission_status=SETTLED),
            _policy(policy_id="cancelled", commission_status=CANCELLED),
        ],
        rows=[
            FinancialRow("settled", "2026-04", "100.00", "Comissão"),
            FinancialRow("cancelled", "2026-04", "100.00", "Comissão"),
        ],
    )

    assert result.entries == ()
    assert result.payable_potential == Decimal("0.00")


def test_non_commissionable_rows_do_not_create_monthly_entries():
    result = build_monthly_financial_engine(
        policies=[_policy()],
        rows=[
            FinancialRow("policy-1", "2026-04", "999.00", "Fee por Vida"),
        ],
    )

    assert all(entry.amount != Decimal("999.00") for entry in result.entries)
    assert result.pending_total == Decimal("0.00")
    assert result.projected_total == Decimal("1200.00")
    assert {entry.state for entry in result.entries} == {PROJETADO}
