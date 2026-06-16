from decimal import Decimal
from app.models import User, UserRole, CnNivel, CnPorte, CnMonthlyGoal, CnMonthlyAppraisal
from app.models.appraisal import AppraisalStatus


def test_user_em_rampagem_defaults_false_and_persists(db_session):
    u = User(email="ramp@test.com", name="Ramp", role=UserRole.CN,
             nivel=CnNivel("CN1"), porte=CnPorte.M)
    db_session.add(u); db_session.flush()
    assert u.em_rampagem is False
    u.em_rampagem = True
    db_session.flush()
    assert db_session.get(User, u.id).em_rampagem is True


def test_goal_cadence_metas_persist(db_session):
    u = User(email="g@test.com", name="G", role=UserRole.CN,
             nivel=CnNivel("CN1"), porte=CnPorte.M)
    db_session.add(u); db_session.flush()
    g = CnMonthlyGoal(cn_id=u.id, month=4, year=2026,
                      sao_target=Decimal("0"), vidas_target=Decimal("0"),
                      negocios_cadencia_meta=Decimal("60"),
                      emails_meta=Decimal("400"),
                      qualis_agendadas_meta=Decimal("10"))
    db_session.add(g); db_session.flush()
    got = db_session.get(CnMonthlyGoal, g.id)
    assert got.negocios_cadencia_meta == Decimal("60.00")
    assert got.emails_meta == Decimal("400.00")
    assert got.qualis_agendadas_meta == Decimal("10.00")


def test_appraisal_rampagem_columns_persist(db_session):
    u = User(email="a@test.com", name="A", role=UserRole.CN,
             nivel=CnNivel("CN3"), porte=CnPorte.M)
    db_session.add(u); db_session.flush()
    a = CnMonthlyAppraisal(
        cn_id=u.id, month=4, year=2026,
        sao_realizado=Decimal("0"), vidas_realizado=Decimal("0"),
        pct_sao=Decimal("0"), pct_vidas=Decimal("0"),
        score_final=Decimal("1"), multiplicador=Decimal("1"),
        commission_amount=Decimal("3300"),
        status=AppraisalStatus.CALCULATING,
        calc_mode="RAMPAGEM_SEM_SAO",
        negocios_cadencia_realizado=Decimal("103"),
        emails_realizado=Decimal("1133"),
        sao_fora_da_meta=1, bonus_sao_amount=Decimal("300"))
    db_session.add(a); db_session.flush()
    got = db_session.get(CnMonthlyAppraisal, a.id)
    assert got.calc_mode == "RAMPAGEM_SEM_SAO"
    assert got.sao_fora_da_meta == 1
    assert got.bonus_sao_amount == Decimal("300.00")
