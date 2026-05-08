"""TDD tests for the CN trimestral bonus calculator (issue #33)."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, CnMonthlyGoal, CnMonthlyAppraisal, CnQuarterBonus,
)
from app.modules.commissions.cn_bonus_calculator import (
    run_cn_quarterly_bonus,
    _bonus_multiplier,
)


def _make_cn(name="CN", salario=Decimal("8000")):
    suffix = uuid.uuid4().hex[:8]
    cn = User(
        email=f"{name.lower()}-{suffix}@x",
        name=name,
        role=UserRole.CN,
        active=True,
        salario_base=salario,
    )
    db.session.add(cn)
    db.session.flush()
    return cn


def _seed_quarter(cn, year, quarter,
                  sao_realizado_per_month, sao_target_per_month,
                  is_final=True):
    months = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}[quarter]
    for m in months:
        db.session.add(CnMonthlyGoal(
            cn_id=cn.id, month=m, year=year,
            sao_target=Decimal(str(sao_target_per_month)),
            vidas_target=Decimal("10"),
        ))
        db.session.add(CnMonthlyAppraisal(
            cn_id=cn.id, month=m, year=year,
            sao_realizado=Decimal(str(sao_realizado_per_month)),
            vidas_realizado=Decimal("8"),
            pct_sao=Decimal("1.0"),
            pct_vidas=Decimal("0.8"),
            score_final=Decimal("0.9"),
            multiplicador=Decimal("1.0"),
            commission_amount=Decimal("0"),
            is_final=is_final,
        ))
    db.session.flush()


# ── Multiplier régua ───────────────────────────────────────────────────


class TestBonusMultiplier:
    def test_below_eligibility_returns_zero(self):
        assert _bonus_multiplier(Decimal("0.79")) == Decimal("0")

    def test_eligible_min_returns_half(self):
        assert _bonus_multiplier(Decimal("0.80")) == Decimal("0.5")

    def test_below_125_returns_one(self):
        assert _bonus_multiplier(Decimal("0.95")) == Decimal("1.0")
        assert _bonus_multiplier(Decimal("1.24")) == Decimal("1.0")

    def test_at_125_returns_one_and_a_half(self):
        assert _bonus_multiplier(Decimal("1.25")) == Decimal("1.5")
        assert _bonus_multiplier(Decimal("2.00")) == Decimal("1.5")


# ── run_cn_quarterly_bonus ─────────────────────────────────────────────


class TestRunCnQuarterlyBonus:
    def test_happy_path_above_eligibility(self, db_session):
        cn = _make_cn(name="HappyCN", salario=Decimal("8000"))
        # 3 months, each: realizado=110, target=100 → trim 330/300 = 1.10 → mult 1.0
        _seed_quarter(cn, year=2026, quarter=1,
                      sao_realizado_per_month=110, sao_target_per_month=100)

        result = run_cn_quarterly_bonus(quarter=1, year=2026)
        assert result["bonuses_computed"] == 1

        bonus = CnQuarterBonus.query.filter_by(
            cn_id=cn.id, quarter=1, year=2026,
        ).first()
        assert bonus is not None
        assert bonus.sao_trim_realizado == Decimal("330.00")
        assert bonus.sao_trim_meta == Decimal("300.00")
        assert bonus.pct_sao_trim == Decimal("1.1000")
        assert bonus.multiplicador == Decimal("1.0")
        assert bonus.bonus_amount == Decimal("8000.00")
        assert bonus.salario_base_snapshot == Decimal("8000")
        assert bonus.is_final is False

    def test_below_eligibility_yields_zero_bonus(self, db_session):
        cn = _make_cn(name="LowCN", salario=Decimal("8000"))
        # realizado=70, target=100 → 210/300 = 0.70 → not eligible
        _seed_quarter(cn, year=2026, quarter=2,
                      sao_realizado_per_month=70, sao_target_per_month=100)

        result = run_cn_quarterly_bonus(quarter=2, year=2026)
        assert result["bonuses_computed"] == 1
        assert result["skipped_below_eligibility"] == 1

        bonus = CnQuarterBonus.query.filter_by(
            cn_id=cn.id, quarter=2, year=2026,
        ).first()
        assert bonus.multiplicador == Decimal("0")
        assert bonus.bonus_amount == Decimal("0.00")

    def test_skips_cn_without_three_final_months(self, db_session):
        cn = _make_cn(name="MissingMonthCN")
        # Only 2 months
        for m in (4, 5):
            db.session.add(CnMonthlyGoal(
                cn_id=cn.id, month=m, year=2026,
                sao_target=Decimal("100"), vidas_target=Decimal("10"),
            ))
            db.session.add(CnMonthlyAppraisal(
                cn_id=cn.id, month=m, year=2026,
                sao_realizado=Decimal("110"),
                vidas_realizado=Decimal("8"),
                pct_sao=Decimal("1.0"), pct_vidas=Decimal("0.8"),
                score_final=Decimal("0.9"), multiplicador=Decimal("1.0"),
                commission_amount=Decimal("0"), is_final=True,
            ))
        db.session.flush()

        result = run_cn_quarterly_bonus(quarter=2, year=2026)
        assert result["bonuses_computed"] == 0
        assert result["skipped_missing_month"] == 1

    def test_skips_cn_with_non_final_month(self, db_session):
        cn = _make_cn(name="NonFinalCN")
        _seed_quarter(cn, year=2026, quarter=3,
                      sao_realizado_per_month=110, sao_target_per_month=100,
                      is_final=False)

        result = run_cn_quarterly_bonus(quarter=3, year=2026)
        assert result["bonuses_computed"] == 0
        assert result["skipped_missing_month"] == 1

    def test_idempotent_rerun_replaces_non_final(self, db_session):
        cn = _make_cn(name="IdempCN", salario=Decimal("8000"))
        _seed_quarter(cn, year=2026, quarter=4,
                      sao_realizado_per_month=110, sao_target_per_month=100)

        first = run_cn_quarterly_bonus(quarter=4, year=2026)
        assert first["bonuses_computed"] == 1
        assert (
            CnQuarterBonus.query.filter_by(quarter=4, year=2026).count() == 1
        )

        # Update one month's realizado and rerun. Old non-final row is
        # replaced by the new one.
        first_appraisal = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, year=2026,
        ).first()
        first_appraisal.sao_realizado = Decimal("200")
        db.session.flush()

        second = run_cn_quarterly_bonus(quarter=4, year=2026)
        assert second["bonuses_computed"] == 1

        bonus = CnQuarterBonus.query.filter_by(
            cn_id=cn.id, quarter=4, year=2026,
        ).first()
        # Now: 200+110+110 = 420 / 300 = 1.40 → mult 1.5
        assert bonus.sao_trim_realizado == Decimal("420.00")
        assert bonus.multiplicador == Decimal("1.5")

    def test_idempotent_rerun_keeps_final_rows(self, db_session):
        cn = _make_cn(name="FinalCN", salario=Decimal("8000"))
        _seed_quarter(cn, year=2027, quarter=1,
                      sao_realizado_per_month=110, sao_target_per_month=100)
        run_cn_quarterly_bonus(quarter=1, year=2027)

        # Mark the bonus final, then mutate the appraisals and rerun.
        bonus = CnQuarterBonus.query.filter_by(
            cn_id=cn.id, quarter=1, year=2027,
        ).first()
        bonus.is_final = True
        db.session.flush()

        first_appraisal = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, year=2027,
        ).first()
        first_appraisal.sao_realizado = Decimal("9999")
        db.session.flush()

        second = run_cn_quarterly_bonus(quarter=1, year=2027)
        assert second["kept_final"] == 1

        bonus_after = CnQuarterBonus.query.filter_by(
            cn_id=cn.id, quarter=1, year=2027,
        ).first()
        # Final row is preserved unchanged.
        assert bonus_after.sao_trim_realizado == Decimal("330.00")
        assert bonus_after.is_final is True

    def test_skips_cn_with_no_salary(self, db_session):
        cn = _make_cn(name="NoSalaryCN", salario=None)
        _seed_quarter(cn, year=2027, quarter=2,
                      sao_realizado_per_month=110, sao_target_per_month=100)

        result = run_cn_quarterly_bonus(quarter=2, year=2027)
        assert result["bonuses_computed"] == 1
        assert result["skipped_no_salary"] == 1

        bonus = CnQuarterBonus.query.filter_by(
            cn_id=cn.id, quarter=2, year=2027,
        ).first()
        assert bonus.bonus_amount == Decimal("0.00")
        assert bonus.salario_base_snapshot is None

    def test_invalid_quarter_raises(self, db_session):
        with pytest.raises(ValueError):
            run_cn_quarterly_bonus(quarter=5, year=2026)
