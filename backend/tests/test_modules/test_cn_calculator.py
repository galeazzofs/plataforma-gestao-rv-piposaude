from decimal import Decimal
import pytest
from app.models import User, UserRole, CnMonthlyGoal, CnMonthlyAppraisal, CnNivel, CnPorte
from app.modules.commissions.cn_calculator import (
    validate_cn_goals,
    run_cn_monthly_appraisal,
    MissingGoalsError,
)
from app.extensions import db


def _make_cn(session, name="Ana", nivel="CN1"):
    u = User(
        email=f"{name.lower()}@test.com",
        name=name,
        role=UserRole.CN,
        nivel=CnNivel(nivel),
        porte=CnPorte.M,
        salario_base=Decimal("3000"),
    )
    session.add(u)
    session.flush()
    return u


def _make_goal(session, cn, month, year, sao=Decimal("100"), vidas=Decimal("50")):
    g = CnMonthlyGoal(
        cn_id=cn.id, month=month, year=year,
        sao_target=sao, vidas_target=vidas,
    )
    session.add(g)
    session.flush()
    return g


class TestValidateCnGoals:
    def test_returns_empty_when_all_goals_present(self, db_session):
        cn = _make_cn(db_session)
        _make_goal(db_session, cn, month=4, year=2026)
        missing = validate_cn_goals(month=4, year=2026)
        assert missing == []

    def test_returns_missing_cn_names(self, db_session):
        _make_cn(db_session, name="Bob")
        # no goal created
        missing = validate_cn_goals(month=4, year=2026)
        assert any("Bob" in m for m in missing)


class TestRunCnMonthlyAppraisal:
    def test_creates_appraisal_for_each_active_cn(self, db_session):
        cn = _make_cn(db_session, name="Carla")
        _make_goal(db_session, cn, month=3, year=2026,
                   sao=Decimal("100"), vidas=Decimal("50"))

        result = run_cn_monthly_appraisal(month=3, year=2026)

        appraisal = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=3, year=2026
        ).first()
        assert appraisal is not None
        assert appraisal.is_final is False
        assert result["appraisals_created"] >= 1

    def test_raises_when_goals_missing(self, db_session):
        _make_cn(db_session, name="Diego")
        with pytest.raises(MissingGoalsError):
            run_cn_monthly_appraisal(month=5, year=2026)

    def test_replaces_non_final_on_rerun(self, db_session):
        cn = _make_cn(db_session, name="Eva")
        _make_goal(db_session, cn, month=6, year=2026)
        run_cn_monthly_appraisal(month=6, year=2026)
        run_cn_monthly_appraisal(month=6, year=2026)
        count = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=6, year=2026
        ).count()
        assert count == 1

    def test_does_not_overwrite_final_appraisal(self, db_session):
        cn = _make_cn(db_session, name="Fabio")
        _make_goal(db_session, cn, month=7, year=2026)
        run_cn_monthly_appraisal(month=7, year=2026)
        appraisal = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=7, year=2026
        ).first()
        appraisal.is_final = True
        db_session.flush()

        # second run should skip this CN
        run_cn_monthly_appraisal(month=7, year=2026)
        assert CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=7, year=2026, is_final=True
        ).count() == 1
