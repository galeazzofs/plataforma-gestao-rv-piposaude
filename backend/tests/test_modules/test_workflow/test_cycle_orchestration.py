"""Orchestration tests for QuarterlyCycle (issue #37)."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal, CnQuarterBonus,
    EvQuarterAchievement, LiderVendasQuarterAppraisal,
    QuarterlyCycle, QuarterlyCycleStatus,
    Team, User, UserRole,
)
from app.modules.workflow.cycle_aggregator import (
    build_cycle_payload, all_components_locked, maybe_lock_cycle,
)
from app.modules.workflow.state_machine import transition_appraisal


def _make_user(role, name, team_id=None, salario=Decimal("8000")):
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"{name.lower().replace(' ', '_')}-{suffix}@x",
        name=name, role=role, active=True,
        salario_base=salario,
        team_id=team_id,
    )
    db.session.add(u)
    db.session.flush()
    return u


def _make_team(name, leader_id=None):
    t = Team(name=name, leader_id=leader_id)
    db.session.add(t)
    db.session.flush()
    return t


@pytest.fixture
def two_teams_setup():
    suffix = uuid.uuid4().hex[:8]
    admin = _make_user(UserRole.ADMIN, f"OrchAdmin-{suffix}")

    lider_a = _make_user(UserRole.LIDER_VENDAS, f"LiderA-{suffix}")
    team_a = _make_team(f"TeamA-{suffix}", leader_id=lider_a.id)
    lider_a.team_id = team_a.id

    lider_b = _make_user(UserRole.LIDER_VENDAS, f"LiderB-{suffix}")
    team_b = _make_team(f"TeamB-{suffix}", leader_id=lider_b.id)
    lider_b.team_id = team_b.id

    ev_a = _make_user(UserRole.EV, f"EVA-{suffix}", team_id=team_a.id)
    cn_a = _make_user(UserRole.CN, f"CNA-{suffix}", team_id=team_a.id)
    ev_b = _make_user(UserRole.EV, f"EVB-{suffix}", team_id=team_b.id)
    cn_b = _make_user(UserRole.CN, f"CNB-{suffix}", team_id=team_b.id)

    cycle = QuarterlyCycle(
        quarter=2, year=2032,
        status=QuarterlyCycleStatus.OPEN,
        created_by=admin.id,
    )
    db.session.add(cycle)
    db.session.flush()

    yield {
        "admin": admin,
        "team_a": team_a, "team_b": team_b,
        "lider_a": lider_a, "lider_b": lider_b,
        "ev_a": ev_a, "cn_a": cn_a,
        "ev_b": ev_b, "cn_b": cn_b,
        "cycle": cycle, "quarter": 2, "year": 2032,
    }


def test_payload_groups_components_by_team(db_session, two_teams_setup):
    s = two_teams_setup
    payload = build_cycle_payload(s["cycle"])
    team_names = [t["team_name"] for t in payload["teams"]]
    assert s["team_a"].name in team_names
    assert s["team_b"].name in team_names

    for team_block in payload["teams"]:
        assert set(team_block["components"].keys()) == {
            "ev_quarter", "cn_monthly", "cn_quarterly_bonus",
            "ev_quarterly_bonus", "leadership",
        }


def _lock_team_components(team_data, ev_user, cn_user, lider_user, quarter, year):
    """Force every component for one team into LOCKED state."""
    db.session.add(EvQuarterAchievement(
        ev_id=ev_user.id, quarter=quarter, year=year,
        total_mrr=Decimal("100000"), mrr_target=Decimal("100000"),
        achievement_pct=Decimal("1.0"), is_final=True,
    ))
    db.session.add(CnQuarterBonus(
        cn_id=cn_user.id, quarter=quarter, year=year,
        sao_trim_realizado=Decimal("100"), sao_trim_meta=Decimal("100"),
        pct_sao_trim=Decimal("1.0"), multiplicador=Decimal("1.0"),
        bonus_amount=Decimal("8000"), is_final=True,
    ))
    last_month = {1: 3, 2: 6, 3: 9, 4: 12}[quarter]
    db.session.add(CnMonthlyAppraisal(
        cn_id=cn_user.id, month=last_month, year=year,
        sao_realizado=Decimal("100"), vidas_realizado=Decimal("10"),
        pct_sao=Decimal("1.0"), pct_vidas=Decimal("1.0"),
        score_final=Decimal("1.0"), multiplicador=Decimal("1.0"),
        commission_amount=Decimal("0"), status=AppraisalStatus.LOCKED,
    ))
    db.session.add(LiderVendasQuarterAppraisal(
        lider_vendas_id=lider_user.id, quarter=quarter, year=year,
        meta_mrr=Decimal("100000"), meta_sql=10,
        realizado_mrr=Decimal("100000"), realizado_sql=10,
        pct_mrr=Decimal("1.0"), pct_sql=Decimal("1.0"),
        multiplicador=Decimal("2.0"), bonus_amount=Decimal("16000"),
        status=AppraisalStatus.LOCKED,
    ))
    db.session.flush()


def test_cycle_does_not_lock_when_team_b_is_behind(db_session, two_teams_setup):
    s = two_teams_setup
    # Team A: every component LOCKED
    _lock_team_components(
        s["team_a"], s["ev_a"], s["cn_a"], s["lider_a"],
        s["quarter"], s["year"],
    )
    # Team B: still pending (no rows)
    # Plus the shared Appraisal — not LOCKED yet
    appraisal = Appraisal(
        quarter=s["quarter"], year=s["year"],
        status=AppraisalStatus.LIDER_REVIEW,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()

    assert all_components_locked(s["cycle"]) is False
    assert maybe_lock_cycle(s["cycle"]) is False
    assert s["cycle"].status == QuarterlyCycleStatus.OPEN


def test_cycle_locks_when_all_teams_complete(db_session, two_teams_setup):
    s = two_teams_setup

    appraisal = Appraisal(
        quarter=s["quarter"], year=s["year"],
        status=AppraisalStatus.DRAFT,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()

    for team, ev_user, cn_user, lider in [
        (s["team_a"], s["ev_a"], s["cn_a"], s["lider_a"]),
        (s["team_b"], s["ev_b"], s["cn_b"], s["lider_b"]),
    ]:
        _lock_team_components(team, ev_user, cn_user, lider,
                              s["quarter"], s["year"])

    # Walk the shared Appraisal to LOCKED. This triggers
    # _maybe_lock_attached_cycle inside transition_appraisal.
    from unittest.mock import patch
    with patch("app.modules.commissions.calculator.run_quarterly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    transition_appraisal(appraisal, AppraisalStatus.LIDER_REVIEW)
    transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)
    transition_appraisal(appraisal, AppraisalStatus.LOCKED, approved_by=s["admin"].id)

    db.session.refresh(s["cycle"])
    assert s["cycle"].status == QuarterlyCycleStatus.LOCKED
    assert s["cycle"].locked_at is not None
