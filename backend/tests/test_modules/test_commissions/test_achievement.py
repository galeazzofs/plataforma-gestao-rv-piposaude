from decimal import Decimal
from app.modules.commissions.achievement import calculate_achievement


def test_achievement_100_percent(db_session):
    """EV with MRR equal to target = 100%."""
    result = calculate_achievement(
        total_mrr_gongos=Decimal("50000"),
        mrr_target=Decimal("50000"),
    )
    assert result == Decimal("1.0")


def test_achievement_50_percent(db_session):
    result = calculate_achievement(
        total_mrr_gongos=Decimal("25000"),
        mrr_target=Decimal("50000"),
    )
    assert result == Decimal("0.5")


def test_achievement_over_100(db_session):
    result = calculate_achievement(
        total_mrr_gongos=Decimal("75000"),
        mrr_target=Decimal("50000"),
    )
    assert result == Decimal("1.5")


def test_achievement_zero_target_returns_zero(db_session):
    result = calculate_achievement(
        total_mrr_gongos=Decimal("10000"),
        mrr_target=Decimal("0"),
    )
    assert result == Decimal("0")
