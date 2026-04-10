from decimal import Decimal
import pytest
from app.models import User, UserRole, Team, Goal, GerenteQuarterAppraisal
from app.modules.commissions.leadership_calculator import (
    run_leadership_appraisal,
    get_leadership_preview,
    _lideranca_multiplier,
)
from app.extensions import db


def _make_gerente(session, name="Gerente", salario=Decimal("10000")):
    u = User(email=f"{name.lower()}@test.com", name=name,
             role=UserRole.GERENTE, salario_base=salario)
    session.add(u)
    session.flush()
    return u


def _make_ev_with_goal(session, team_id, name, mrr_target, quarter, year):
    ev = User(email=f"{name.lower()}@test.com", name=name,
              role=UserRole.EV, team_id=team_id)
    session.add(ev)
    session.flush()
    g = Goal(ev_id=ev.id, quarter=quarter, year=year, mrr_target=mrr_target)
    session.add(g)
    session.flush()
    return ev


def _make_team(session, gerente):
    t = Team(name="Time Teste", leader_id=gerente.id)
    session.add(t)
    session.flush()
    gerente.team_id = t.id
    session.flush()
    return t


def _make_gerente_with_team(session, name="Gerente", salario=Decimal("10000")):
    gerente = _make_gerente(session, name=name, salario=salario)
    team = _make_team(session, gerente)
    ev = User(
        email=f"{name.lower().replace(' ', '_')}_ev@test.com",
        name=f"{name} EV",
        role=UserRole.EV,
        team_id=team.id,
    )
    session.add(ev)
    session.flush()
    return gerente, team


def _make_goal(session, ev, quarter, year, mrr_target):
    g = Goal(ev_id=ev.id, quarter=quarter, year=year, mrr_target=mrr_target)
    session.add(g)
    session.flush()
    return g


class TestLiderancaMultiplier:
    def test_zero_mrr_returns_zero(self):
        assert _lideranca_multiplier(Decimal("0.5"), Decimal("0.5")) == Decimal("0")

    def test_mrr_60_sql_80_returns_0_75(self):
        assert _lideranca_multiplier(Decimal("0.65"), Decimal("0.82")) == Decimal("0.75")

    def test_mrr_95_sql_110_returns_3_25(self):
        assert _lideranca_multiplier(Decimal("1.00"), Decimal("1.10")) == Decimal("3.25")

    def test_max_mrr_110_sql_110_returns_4_0(self):
        assert _lideranca_multiplier(Decimal("1.10"), Decimal("1.15")) == Decimal("4.0")


class TestRunLeadershipAppraisal:
    def test_computes_gerente_bonus(self, db_session):
        gerente = _make_gerente(db_session)
        team = _make_team(db_session, gerente)
        _make_ev_with_goal(db_session, team.id, "EV1",
                           Decimal("100000"), quarter=1, year=2026)
        _make_ev_with_goal(db_session, team.id, "EV2",
                           Decimal("100000"), quarter=1, year=2026)

        # meta_mrr = 90% × 200,000 = 180,000
        # realizado_mrr = 200,000 → pct_mrr = 1.11 (≥ 110%)
        # meta_sql = 10, realizado_sql = 11 → pct_sql = 1.10 (≥ 110%)
        # multiplier = 4.0, bonus = 10000 * 4.0 = 40000
        inputs = [{
            "gerente_id": str(gerente.id),
            "meta_sql": 10,
            "realizado_mrr": "200000",
            "realizado_sql": 11,
        }]
        result = run_leadership_appraisal(quarter=1, year=2026, inputs=inputs)

        appraisal = GerenteQuarterAppraisal.query.filter_by(
            gerente_id=gerente.id, quarter=1, year=2026
        ).first()
        assert appraisal is not None
        assert appraisal.meta_mrr == Decimal("180000.00")
        assert appraisal.bonus_amount == Decimal("40000.00")
        assert result["appraisals_created"] == 1

    def test_skips_final_appraisal(self, db_session):
        gerente, team = _make_gerente_with_team(db_session, name="Final Gerente")
        ev = team.members[0]
        _make_goal(db_session, ev, quarter=3, year=2026, mrr_target=Decimal("100000"))

        # Create a final appraisal manually
        import uuid
        final = GerenteQuarterAppraisal(
            gerente_id=gerente.id,
            quarter=3, year=2026,
            meta_mrr=Decimal("90000"),
            meta_sql=10,
            realizado_mrr=Decimal("95000"),
            realizado_sql=10,
            pct_mrr=Decimal("1.0556"),
            pct_sql=Decimal("1.0000"),
            multiplicador=Decimal("3.0"),
            bonus_amount=Decimal("30000"),
            is_final=True,
        )
        db_session.add(final)
        db_session.flush()

        result = run_leadership_appraisal(
            quarter=3, year=2026,
            inputs=[{
                "gerente_id": str(gerente.id),
                "meta_sql": 10,
                "realizado_mrr": "95000",
                "realizado_sql": 10,
            }],
        )
        assert result["appraisals_created"] == 0

    def test_zero_meta_sql_does_not_raise(self, db_session):
        gerente, team = _make_gerente_with_team(db_session, name="ZeroSQL Gerente")
        ev = team.members[0]
        _make_goal(db_session, ev, quarter=4, year=2026, mrr_target=Decimal("100000"))

        result = run_leadership_appraisal(
            quarter=4, year=2026,
            inputs=[{
                "gerente_id": str(gerente.id),
                "meta_sql": 0,
                "realizado_mrr": "50000",
                "realizado_sql": 0,
            }],
        )
        assert result["appraisals_created"] == 1
        appraisal = GerenteQuarterAppraisal.query.filter_by(
            gerente_id=gerente.id, quarter=4, year=2026
        ).first()
        assert appraisal.pct_sql == Decimal("0")

    def test_skips_gerente_with_no_salary(self, db_session):
        gerente = User(
            email="nosalary@test.com",
            name="No Salary Gerente",
            role=UserRole.GERENTE,
            salario_base=None,
        )
        db_session.add(gerente)
        db_session.flush()
        team = Team(name="Team NS", leader_id=gerente.id)
        db_session.add(team)
        db_session.flush()

        result = run_leadership_appraisal(
            quarter=2, year=2026,
            inputs=[{
                "gerente_id": str(gerente.id),
                "meta_sql": 10,
                "realizado_mrr": "50000",
                "realizado_sql": 8,
            }],
        )
        assert result["appraisals_created"] == 0

    def test_gerente_with_no_team_gets_zero_meta_mrr(self, db_session):
        # GERENTE with no team: meta_mrr=0, so pct_mrr=0 → 0x multiplier → 0 bonus
        gerente = User(
            email="noteam@test.com",
            name="No Team Gerente",
            role=UserRole.GERENTE,
            salario_base=Decimal("10000"),
        )
        db_session.add(gerente)
        db_session.flush()
        # No team created

        result = run_leadership_appraisal(
            quarter=1, year=2027,
            inputs=[{
                "gerente_id": str(gerente.id),
                "meta_sql": 10,
                "realizado_mrr": "50000",
                "realizado_sql": 8,
            }],
        )
        assert result["appraisals_created"] == 1
        appraisal = GerenteQuarterAppraisal.query.filter_by(
            gerente_id=gerente.id, quarter=1, year=2027
        ).first()
        assert appraisal is not None
        assert appraisal.meta_mrr == Decimal("0")
        assert appraisal.bonus_amount == Decimal("0")
