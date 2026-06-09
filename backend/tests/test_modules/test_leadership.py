from decimal import Decimal
import uuid
import pytest
from app.models import (
    Appraisal, AppraisalStatus, BenefitType, Client, EvValidation, Goal,
    LiderVendasQuarterAppraisal, Policy, Segment, Team, User, UserRole,
    ValidationStatus,
)
from app.modules.commissions.leadership_calculator import (
    run_leadership_appraisal,
    get_leadership_preview,
    _lideranca_multiplier,
)
from app.auth.jwt_manager import create_access_token
from app.extensions import db


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _make_lider(session, name="Lider", salario=Decimal("10000")):
    u = User(email=f"{name.lower()}@test.com", name=name,
             role=UserRole.LIDER_VENDAS, salario_base=salario)
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


def _make_team(session, lider):
    t = Team(name="Time Teste", leader_id=lider.id)
    session.add(t)
    session.flush()
    lider.team_id = t.id
    session.flush()
    return t


def _make_lider_with_team(session, name="Lider", salario=Decimal("10000")):
    lider = _make_lider(session, name=name, salario=salario)
    team = _make_team(session, lider)
    ev = User(
        email=f"{name.lower().replace(' ', '_')}_ev@test.com",
        name=f"{name} EV",
        role=UserRole.EV,
        team_id=team.id,
    )
    session.add(ev)
    session.flush()
    return lider, team


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
    def test_computes_lider_vendas_bonus(self, db_session):
        lider = _make_lider(db_session)
        team = _make_team(db_session, lider)
        _make_ev_with_goal(db_session, team.id, "EV1",
                           Decimal("100000"), quarter=1, year=2026)
        _make_ev_with_goal(db_session, team.id, "EV2",
                           Decimal("100000"), quarter=1, year=2026)

        # meta_mrr = 90% × 200,000 = 180,000
        # realizado_mrr = 200,000 → pct_mrr = 1.11 (≥ 110%)
        # meta_sql = 10, realizado_sql = 11 → pct_sql = 1.10 (≥ 110%)
        # multiplier = 4.0, bonus = 10000 * 4.0 = 40000
        inputs = [{
            "lider_vendas_id": str(lider.id),
            "meta_sql": 10,
            "realizado_mrr": "200000",
            "realizado_sql": 11,
        }]
        result = run_leadership_appraisal(quarter=1, year=2026, inputs=inputs)

        appraisal = LiderVendasQuarterAppraisal.query.filter_by(
            lider_vendas_id=lider.id, quarter=1, year=2026
        ).first()
        assert appraisal is not None
        assert appraisal.meta_mrr == Decimal("180000.00")
        assert appraisal.bonus_amount == Decimal("40000.00")
        assert result["appraisals_created"] == 1

    def test_skips_final_appraisal(self, db_session):
        lider, team = _make_lider_with_team(db_session, name="Final Lider")
        ev = team.members[0]
        _make_goal(db_session, ev, quarter=3, year=2026, mrr_target=Decimal("100000"))

        # Create a final appraisal manually
        import uuid
        final = LiderVendasQuarterAppraisal(
            lider_vendas_id=lider.id,
            quarter=3, year=2026,
            meta_mrr=Decimal("90000"),
            meta_sql=10,
            realizado_mrr=Decimal("95000"),
            realizado_sql=10,
            pct_mrr=Decimal("1.0556"),
            pct_sql=Decimal("1.0000"),
            multiplicador=Decimal("3.0"),
            bonus_amount=Decimal("30000"),
            status=AppraisalStatus.LOCKED,
        )
        db_session.add(final)
        db_session.flush()

        result = run_leadership_appraisal(
            quarter=3, year=2026,
            inputs=[{
                "lider_vendas_id": str(lider.id),
                "meta_sql": 10,
                "realizado_mrr": "95000",
                "realizado_sql": 10,
            }],
        )
        assert result["appraisals_created"] == 0

    def test_zero_meta_sql_does_not_raise(self, db_session):
        lider, team = _make_lider_with_team(db_session, name="ZeroSQL Lider")
        ev = team.members[0]
        _make_goal(db_session, ev, quarter=4, year=2026, mrr_target=Decimal("100000"))

        result = run_leadership_appraisal(
            quarter=4, year=2026,
            inputs=[{
                "lider_vendas_id": str(lider.id),
                "meta_sql": 0,
                "realizado_mrr": "50000",
                "realizado_sql": 0,
            }],
        )
        assert result["appraisals_created"] == 1
        appraisal = LiderVendasQuarterAppraisal.query.filter_by(
            lider_vendas_id=lider.id, quarter=4, year=2026
        ).first()
        assert appraisal.pct_sql == Decimal("0")

    def test_skips_lider_vendas_with_no_salary(self, db_session):
        lider = User(
            email="nosalary@test.com",
            name="No Salary Lider",
            role=UserRole.LIDER_VENDAS,
            salario_base=None,
        )
        db_session.add(lider)
        db_session.flush()
        team = Team(name="Team NS", leader_id=lider.id)
        db_session.add(team)
        db_session.flush()

        result = run_leadership_appraisal(
            quarter=2, year=2026,
            inputs=[{
                "lider_vendas_id": str(lider.id),
                "meta_sql": 10,
                "realizado_mrr": "50000",
                "realizado_sql": 8,
            }],
        )
        assert result["appraisals_created"] == 0

    def test_lider_vendas_with_no_team_gets_zero_meta_mrr(self, db_session):
        # LIDER_VENDAS with no team: meta_mrr=0, so pct_mrr=0 → 0x multiplier → 0 bonus
        lider = User(
            email="noteam@test.com",
            name="No Team Lider",
            role=UserRole.LIDER_VENDAS,
            salario_base=Decimal("10000"),
        )
        db_session.add(lider)
        db_session.flush()
        # No team created

        result = run_leadership_appraisal(
            quarter=1, year=2027,
            inputs=[{
                "lider_vendas_id": str(lider.id),
                "meta_sql": 10,
                "realizado_mrr": "50000",
                "realizado_sql": 8,
            }],
        )
        assert result["appraisals_created"] == 1
        appraisal = LiderVendasQuarterAppraisal.query.filter_by(
            lider_vendas_id=lider.id, quarter=1, year=2027
        ).first()
        assert appraisal is not None
        assert appraisal.meta_mrr == Decimal("0")
        assert appraisal.bonus_amount == Decimal("0")


class TestPreviewAutoFill:
    def test_realizado_mrr_auto_sums_team_total_mrr(self, db_session):
        from app.models import EvQuarterAchievement
        lider = _make_lider(db_session, name="AutoLider", salario=Decimal("10000"))
        team = _make_team(db_session, lider)

        # Two EVs in the team with achievements
        ev1 = User(email="auto-ev1@x", name="EV1",
                   role=UserRole.EV, team_id=team.id, active=True)
        ev2 = User(email="auto-ev2@x", name="EV2",
                   role=UserRole.EV, team_id=team.id, active=True)
        db_session.add_all([ev1, ev2])
        db_session.flush()

        db_session.add_all([
            EvQuarterAchievement(
                ev_id=ev1.id, quarter=2, year=2027,
                total_mrr=Decimal("80000"),
                mrr_target=Decimal("100000"),
                achievement_pct=Decimal("0.80"),
            ),
            EvQuarterAchievement(
                ev_id=ev2.id, quarter=2, year=2027,
                total_mrr=Decimal("120000"),
                mrr_target=Decimal("100000"),
                achievement_pct=Decimal("1.20"),
            ),
        ])
        db_session.flush()

        preview = get_leadership_preview(quarter=2, year=2027)
        row = next((r for r in preview if r["lider_vendas_id"] == str(lider.id)), None)
        assert row is not None
        assert row["realizado_mrr_auto"] == "200000.00"

    def test_realizado_mrr_auto_zero_when_no_achievements(self, db_session):
        lider = _make_lider(db_session, name="NoAchLider")
        _make_team(db_session, lider)

        preview = get_leadership_preview(quarter=2, year=2028)
        row = next((r for r in preview if r["lider_vendas_id"] == str(lider.id)), None)
        assert row is not None
        assert row["realizado_mrr_auto"] == "0.00"


class TestLeadershipTransitions:
    def test_full_chain_to_locked(self, db_session):
        from app.modules.workflow.state_machine import (
            transition_lider_vendas_appraisal,
        )
        lider = _make_lider(db_session, name="TxLider")
        appraisal = LiderVendasQuarterAppraisal(
            lider_vendas_id=lider.id, quarter=4, year=2027,
            meta_mrr=Decimal("100000"), meta_sql=10,
            realizado_mrr=Decimal("100000"), realizado_sql=10,
            pct_mrr=Decimal("1.0"), pct_sql=Decimal("1.0"),
            multiplicador=Decimal("2.0"), bonus_amount=Decimal("20000"),
            status=AppraisalStatus.DRAFT,
        )
        db_session.add(appraisal)
        db_session.flush()

        for s in [
            AppraisalStatus.CALCULATING,
            AppraisalStatus.VALIDATING,
            AppraisalStatus.LIDER_REVIEW,
            AppraisalStatus.REVOPS_REVIEW,
            AppraisalStatus.LOCKED,
        ]:
            transition_lider_vendas_appraisal(appraisal, s)

        assert appraisal.is_final is True
        assert appraisal.status == AppraisalStatus.LOCKED

    def test_lider_transition_rechecks_monthly_appraisals_in_quarter(
        self, client, db_session
    ):
        period_year = 2080 + int(uuid.uuid4().hex[:2], 16)
        admin = User(
            email="lider-hook-admin@test.com",
            name="Admin",
            role=UserRole.ADMIN,
            active=True,
        )
        lider, team = _make_lider_with_team(
            db_session, name="Hook Lider", salario=Decimal("10000"),
        )
        ev = next(member for member in team.members if member.role == UserRole.EV)
        ev.active = True
        db_session.add(admin)
        db_session.flush()

        client_obj = Client(
            name="Hook Client",
            name_normalized="hook client",
            ev_id=ev.id,
        )
        db_session.add(client_obj)
        db_session.flush()
        policy = Policy(
            hubspot_ticket_id="HOOK-T1",
            ev_id=ev.id,
            client_id=client_obj.id,
            segment=Segment.M,
            benefit_type=BenefitType.SAUDE,
        )
        monthly = Appraisal(
            month=4,
            year=period_year,
            status=AppraisalStatus.VALIDATING,
            created_by=admin.id,
        )
        leadership = LiderVendasQuarterAppraisal(
            lider_vendas_id=lider.id,
            quarter=2,
            year=period_year,
            meta_mrr=Decimal("100000"),
            meta_sql=10,
            realizado_mrr=Decimal("100000"),
            realizado_sql=10,
            pct_mrr=Decimal("1.0"),
            pct_sql=Decimal("1.0"),
            multiplicador=Decimal("2.0"),
            bonus_amount=Decimal("20000"),
            status=AppraisalStatus.VALIDATING,
        )
        db_session.add_all([policy, monthly, leadership])
        db_session.flush()
        validation = EvValidation(
            appraisal_id=monthly.id,
            policy_id=policy.id,
            ev_id=ev.id,
            status=ValidationStatus.APPROVED,
        )
        db_session.add(validation)
        db_session.commit()

        resp = client.post(
            f"/api/v1/commissions/leadership/appraisal/{leadership.id}/transition",
            json={"to": "LIDER_REVIEW"},
            headers=_auth(lider),
        )

        assert resp.status_code == 200
        db_session.refresh(monthly)
        assert monthly.status == AppraisalStatus.LIDER_REVIEW
