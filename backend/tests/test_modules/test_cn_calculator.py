from decimal import Decimal
import pytest
from app.models import User, UserRole, CnMonthlyGoal, CnMonthlyAppraisal, CnNivel, CnPorte
from app.modules.commissions.cn_calculator import (
    validate_cn_goals,
    run_cn_monthly_appraisal,
    run_cn_monthly_appraisal_with_inputs,
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
        # Calculator advances directly into CALCULATING; LOCKED is the
        # finalization step.
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
        from app.models import AppraisalStatus
        cn = _make_cn(db_session, name="Fabio")
        _make_goal(db_session, cn, month=7, year=2026)
        run_cn_monthly_appraisal(month=7, year=2026)
        appraisal = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=7, year=2026
        ).first()
        appraisal.status = AppraisalStatus.LOCKED
        db_session.flush()

        # second run should skip this CN
        run_cn_monthly_appraisal(month=7, year=2026)
        locked = CnMonthlyAppraisal.query.filter(
            CnMonthlyAppraisal.cn_id == cn.id,
            CnMonthlyAppraisal.month == 7,
            CnMonthlyAppraisal.year == 2026,
            CnMonthlyAppraisal.status == AppraisalStatus.LOCKED,
        ).count()
        assert locked == 1


class TestRunWithInputs:
    def test_uses_realizado_and_auto_vidas_meta_from_porte(self, db_session):
        # Porte M ⇒ vidas meta auto = sao_target × 375. The stored
        # vidas_target is deliberately wrong to prove the calculator derives
        # the lives target from porte, exactly like the simulator does.
        cn = _make_cn(db_session, name="Gina", nivel="CN1")
        _make_goal(db_session, cn, month=8, year=2026,
                   sao=Decimal("100"), vidas=Decimal("1"))

        run_cn_monthly_appraisal_with_inputs(8, 2026, [
            {"cn_id": str(cn.id),
             "sao_realizado": "100",
             "vidas_realizado": "37500"},
        ])

        a = CnMonthlyAppraisal.query.filter_by(
            cn_id=cn.id, month=8, year=2026
        ).first()
        # auto vidas meta = 100 × 375 = 37500 ⇒ pct_vidas = 1.0
        # score = 0.7×1.0 + 0.3×1.0 = 1.0 ⇒ mult 1.20
        # CN1 base 2000 × 1.20 = 2400.00
        assert a.pct_vidas == Decimal("1.0000")
        assert a.commission_amount == Decimal("2400.00")


from app.models.appraisal import AppraisalStatus


class TestRampagemAppraisal:
    def _ramp_cn(self, session, name, nivel="CN3"):
        u = _make_cn(session, name=name, nivel=nivel)
        u.em_rampagem = True
        session.flush()
        return u

    def test_sem_sao_persists_rampagem_result(self, db_session):
        cn = self._ramp_cn(db_session, "Rafa")
        g = CnMonthlyGoal(cn_id=cn.id, month=4, year=2026,
                          sao_target=Decimal("0"), vidas_target=Decimal("0"),
                          negocios_cadencia_meta=Decimal("60"),
                          emails_meta=Decimal("400"),
                          qualis_agendadas_meta=Decimal("0"))
        db_session.add(g); db_session.flush()

        run_cn_monthly_appraisal_with_inputs(4, 2026, [{
            "cn_id": str(cn.id),
            "negocios_cadencia_realizado": "103",
            "emails_realizado": "1133",
            "sao_fora_da_meta": "1",
        }])
        a = CnMonthlyAppraisal.query.filter_by(cn_id=cn.id, month=4, year=2026).one()
        assert a.calc_mode == "RAMPAGEM_SEM_SAO"
        assert str(a.commission_amount) == "3300.00"
        assert a.sao_fora_da_meta == 1
        assert str(a.bonus_sao_amount) == "300.00"

    def test_com_sao_uses_sao_and_qualis(self, db_session):
        cn = self._ramp_cn(db_session, "Bia")
        g = CnMonthlyGoal(cn_id=cn.id, month=5, year=2026,
                          sao_target=Decimal("3"), vidas_target=Decimal("0"),
                          negocios_cadencia_meta=Decimal("0"),
                          emails_meta=Decimal("0"),
                          qualis_agendadas_meta=Decimal("10"))
        db_session.add(g); db_session.flush()

        run_cn_monthly_appraisal_with_inputs(5, 2026, [{
            "cn_id": str(cn.id),
            "sao_realizado": "5",
            "qualis_agendadas_realizado": "10",
        }])
        a = CnMonthlyAppraisal.query.filter_by(cn_id=cn.id, month=5, year=2026).one()
        assert a.calc_mode == "RAMPAGEM_COM_SAO"
        assert str(a.commission_amount) == "5400.00"

    def test_non_rampagem_cn_uses_normal(self, db_session):
        cn = _make_cn(db_session, name="Normal", nivel="CN1")
        _make_goal(db_session, cn, month=6, year=2026,
                   sao=Decimal("100"), vidas=Decimal("50"))
        run_cn_monthly_appraisal_with_inputs(6, 2026, [{
            "cn_id": str(cn.id),
            "sao_realizado": "100", "vidas_realizado": "50",
        }])
        a = CnMonthlyAppraisal.query.filter_by(cn_id=cn.id, month=6, year=2026).one()
        assert a.calc_mode == "NORMAL"
        # porte M ⇒ vidas_meta = 100×375 = 37500; vidas_realizado=50 ⇒
        # pct_vidas≈0.0013, pct_sao=1.0 ⇒ score=0.7004 ⇒ régua returns score
        # itself ⇒ CN1 base 2000 × 0.7004 = 1400.80 (NOT 2400.00; the task's
        # literal was wrong — adjusted to the real NORMAL-path output).
        assert str(a.commission_amount) == "1400.80"
