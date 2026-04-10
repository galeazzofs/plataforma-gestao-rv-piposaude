from decimal import Decimal
import pytest
from app.models import User, UserRole, EvQuarterAchievement
from app.modules.commissions.ev_bonus import run_ev_quarterly_bonus, _mrr_multiplier
from app.extensions import db


def _make_ev(session, name="João", salario=Decimal("5000")):
    u = User(
        email=f"{name.lower()}@test.com",
        name=name,
        role=UserRole.EV,
        salario_base=salario,
    )
    session.add(u)
    session.flush()
    return u


def _make_achievement(session, ev, quarter, year, achievement_pct):
    ach = EvQuarterAchievement(
        ev_id=ev.id,
        quarter=quarter,
        year=year,
        total_mrr=Decimal("0"),
        mrr_target=Decimal("100000"),
        achievement_pct=achievement_pct,
        is_final=False,
    )
    session.add(ach)
    session.flush()
    return ach


class TestMrrMultiplier:
    def test_below_80pct_returns_zero(self):
        assert _mrr_multiplier(Decimal("0.79")) == Decimal("0")

    def test_at_80pct_returns_0_5(self):
        assert _mrr_multiplier(Decimal("0.80")) == Decimal("0.5")

    def test_at_95pct_returns_1_0(self):
        assert _mrr_multiplier(Decimal("0.95")) == Decimal("1.0")

    def test_at_125pct_returns_1_5(self):
        assert _mrr_multiplier(Decimal("1.25")) == Decimal("1.5")


class TestRunEvQuarterlyBonus:
    def test_computes_bonus_for_ev_with_achievement(self, db_session):
        ev = _make_ev(db_session, name="Lucas", salario=Decimal("6000"))
        _make_achievement(db_session, ev, quarter=1, year=2026,
                          achievement_pct=Decimal("1.00"))  # 100% → 1.0x

        result = run_ev_quarterly_bonus(quarter=1, year=2026)

        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev.id, quarter=1, year=2026
        ).first()
        assert ach.bonus_amount == Decimal("6000.00")
        assert ach.salario_base_snapshot == Decimal("6000")
        assert result["bonuses_computed"] >= 1

    def test_below_80pct_sets_zero_bonus(self, db_session):
        ev = _make_ev(db_session, name="Maria", salario=Decimal("5000"))
        _make_achievement(db_session, ev, quarter=2, year=2026,
                          achievement_pct=Decimal("0.50"))

        run_ev_quarterly_bonus(quarter=2, year=2026)

        ach = EvQuarterAchievement.query.filter_by(
            ev_id=ev.id, quarter=2, year=2026
        ).first()
        assert ach.bonus_amount == Decimal("0.00")

    def test_skips_ev_with_no_salario_base(self, db_session):
        ev = _make_ev(db_session, name="Pedro", salario=None)
        _make_achievement(db_session, ev, quarter=3, year=2026,
                          achievement_pct=Decimal("1.00"))

        result = run_ev_quarterly_bonus(quarter=3, year=2026)
        assert result["skipped_no_salary"] >= 1
