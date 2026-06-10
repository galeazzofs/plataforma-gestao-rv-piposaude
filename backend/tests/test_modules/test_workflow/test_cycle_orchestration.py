"""Orchestration tests for MonthlyCycle.

The cycle is monthly and holds the apuração sequence: Apuração EV →
Apuração CN → (quarter-end months only) Bônus CN, Bônus EV and Bônus
Liderança.
"""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal, CnQuarterBonus,
    EvQuarterAchievement, LiderVendasQuarterAppraisal,
    MonthlyCycle, MonthlyCycleStatus,
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
    """Two teams plus a quarter-end cycle (June = month 6, Q2)."""
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

    cycle = MonthlyCycle(
        month=6, year=2032,
        status=MonthlyCycleStatus.OPEN,
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
        "cycle": cycle, "month": 6, "quarter": 2, "year": 2032,
    }


def _add_cn_monthly(cn_user, month, year, status):
    row = CnMonthlyAppraisal(
        cn_id=cn_user.id, month=month, year=year,
        sao_realizado=Decimal("100"), vidas_realizado=Decimal("10"),
        pct_sao=Decimal("1.0"), pct_vidas=Decimal("1.0"),
        score_final=Decimal("1.0"), multiplicador=Decimal("1.0"),
        commission_amount=Decimal("0"), status=status,
    )
    db.session.add(row)
    return row


def _add_quarter_bonuses(ev_user, cn_user, lider_user, quarter, year,
                         leadership_status=AppraisalStatus.LOCKED):
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
    row = LiderVendasQuarterAppraisal(
        lider_vendas_id=lider_user.id, quarter=quarter, year=year,
        meta_mrr=Decimal("100000"), meta_sql=10,
        realizado_mrr=Decimal("100000"), realizado_sql=10,
        pct_mrr=Decimal("1.0"), pct_sql=Decimal("1.0"),
        multiplicador=Decimal("2.0"), bonus_amount=Decimal("16000"),
        status=leadership_status,
    )
    db.session.add(row)
    return row


def _lock_team_components(ev_user, cn_user, lider_user, month, year):
    """Force every quarter-end component for one team into LOCKED state."""
    quarter = (month - 1) // 3 + 1
    _add_quarter_bonuses(ev_user, cn_user, lider_user, quarter, year)
    _add_cn_monthly(cn_user, month, year, AppraisalStatus.LOCKED)
    db.session.flush()


def _walk_appraisal_to_locked(appraisal, admin):
    from unittest.mock import patch
    with patch("app.modules.commissions.calculator.run_monthly_appraisal"):
        transition_appraisal(appraisal, AppraisalStatus.CALCULATING)
    transition_appraisal(appraisal, AppraisalStatus.VALIDATING)
    transition_appraisal(appraisal, AppraisalStatus.LIDER_REVIEW)
    transition_appraisal(appraisal, AppraisalStatus.REVOPS_REVIEW)
    transition_appraisal(appraisal, AppraisalStatus.LOCKED,
                         approved_by=admin.id)


def test_payload_quarter_end_has_full_sequence(db_session, two_teams_setup):
    s = two_teams_setup
    payload = build_cycle_payload(s["cycle"])
    assert payload["month"] == 6
    assert payload["quarter"] == 2
    assert payload["is_quarter_end"] is True
    assert payload["sequence"] == [
        "ev_apuracao", "cn_apuracao", "cn_bonus", "ev_bonus",
        "leadership_bonus",
    ]
    assert "teams" not in payload
    assert set(payload["components"].keys()) == {
        "ev_apuracao", "cn_apuracao", "cn_bonus", "ev_bonus",
        "leadership_bonus",
    }


def test_payload_mid_quarter_has_only_apuracoes(db_session, two_teams_setup):
    s = two_teams_setup
    cycle = MonthlyCycle(
        month=5, year=s["year"],
        status=MonthlyCycleStatus.OPEN,
        created_by=s["admin"].id,
    )
    db.session.add(cycle)
    db.session.flush()

    payload = build_cycle_payload(cycle)
    assert payload["is_quarter_end"] is False
    assert payload["sequence"] == ["ev_apuracao", "cn_apuracao"]
    assert "teams" not in payload
    assert set(payload["components"].keys()) == {"ev_apuracao", "cn_apuracao"}


def test_cycle_does_not_lock_while_any_cn_row_missing(db_session, two_teams_setup):
    """A LOCKED-only CN row set that misses an active CN must hold the
    component (and the cycle) open — the per-team payload guaranteed this
    via the missing team's PENDING; the global payload uses `expected`."""
    s = two_teams_setup
    # CN A: every component LOCKED; CN B: no rows at all.
    _lock_team_components(
        s["ev_a"], s["cn_a"], s["lider_a"], s["month"], s["year"],
    )
    appraisal = Appraisal(
        month=s["month"], year=s["year"],
        status=AppraisalStatus.LIDER_REVIEW,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()

    components = build_cycle_payload(s["cycle"])["components"]
    assert components["cn_apuracao"]["rows"] == 1
    assert components["cn_apuracao"]["expected"] == 2
    assert components["cn_apuracao"]["status"] == "CALCULATING"

    assert all_components_locked(s["cycle"]) is False
    assert maybe_lock_cycle(s["cycle"]) is False
    assert s["cycle"].status == MonthlyCycleStatus.OPEN


def test_mid_quarter_cycle_locks_without_bonuses(db_session, two_teams_setup):
    """A non-quarter-end cycle only gates on Apuração EV + Apuração CN —
    no quarterly bonus rows are required."""
    s = two_teams_setup
    cycle = MonthlyCycle(
        month=5, year=s["year"],
        status=MonthlyCycleStatus.OPEN,
        created_by=s["admin"].id,
    )
    db.session.add(cycle)

    for cn_user in (s["cn_a"], s["cn_b"]):
        _add_cn_monthly(cn_user, 5, s["year"], AppraisalStatus.LOCKED)
    appraisal = Appraisal(
        month=5, year=s["year"],
        status=AppraisalStatus.DRAFT,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()

    # The last LOCK triggers _maybe_lock_attached_cycle inside
    # transition_appraisal.
    _walk_appraisal_to_locked(appraisal, s["admin"])

    db.session.refresh(cycle)
    assert cycle.status == MonthlyCycleStatus.LOCKED
    assert cycle.locked_at is not None


def test_quarter_end_cycle_locks_when_all_teams_complete(
    db_session, two_teams_setup,
):
    s = two_teams_setup
    for ev_user, cn_user, lider in [
        (s["ev_a"], s["cn_a"], s["lider_a"]),
        (s["ev_b"], s["cn_b"], s["lider_b"]),
    ]:
        _lock_team_components(ev_user, cn_user, lider, s["month"], s["year"])

    appraisal = Appraisal(
        month=s["month"], year=s["year"],
        status=AppraisalStatus.DRAFT,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()

    _walk_appraisal_to_locked(appraisal, s["admin"])

    db.session.refresh(s["cycle"])
    assert s["cycle"].status == MonthlyCycleStatus.LOCKED
    assert s["cycle"].locked_at is not None


def test_cycle_locks_from_cn_monthly_when_appraisal_already_locked(
    db_session, two_teams_setup,
):
    """Issue #37b: a cycle should also auto-LOCK when the *last* component
    to be locked is a CnMonthlyAppraisal (not the Appraisal)."""
    from app.modules.workflow.state_machine import (
        transition_cn_monthly_appraisal,
    )

    s = two_teams_setup

    # Quarter bonuses done for both teams; CN A LOCKED, CN B behind.
    for ev_user, cn_user, lider in [
        (s["ev_a"], s["cn_a"], s["lider_a"]),
        (s["ev_b"], s["cn_b"], s["lider_b"]),
    ]:
        _add_quarter_bonuses(ev_user, cn_user, lider,
                             s["quarter"], s["year"])
    _add_cn_monthly(s["cn_a"], s["month"], s["year"], AppraisalStatus.LOCKED)
    cn_b_row = _add_cn_monthly(
        s["cn_b"], s["month"], s["year"], AppraisalStatus.REVOPS_REVIEW,
    )
    db.session.flush()

    appraisal = Appraisal(
        month=s["month"], year=s["year"],
        status=AppraisalStatus.REVOPS_REVIEW,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()
    transition_appraisal(
        appraisal, AppraisalStatus.LOCKED, approved_by=s["admin"].id,
    )

    # Cycle should still be OPEN — cn_b_row is the last gate.
    db.session.refresh(s["cycle"])
    assert s["cycle"].status == MonthlyCycleStatus.OPEN

    # Lock the final CN monthly row. This must trigger cycle re-eval.
    transition_cn_monthly_appraisal(cn_b_row, AppraisalStatus.LOCKED)
    db.session.flush()

    db.session.refresh(s["cycle"])
    assert s["cycle"].status == MonthlyCycleStatus.LOCKED
    assert s["cycle"].locked_at is not None


def test_cycle_locks_from_leadership_lock(db_session, two_teams_setup):
    """The quarterly leadership appraisal maps to the quarter-end month's
    cycle: its LOCK must re-evaluate that cycle."""
    from app.modules.workflow.state_machine import (
        transition_lider_vendas_appraisal,
    )

    s = two_teams_setup

    _lock_team_components(
        s["ev_a"], s["cn_a"], s["lider_a"], s["month"], s["year"],
    )
    # Team B: everything done except the leadership row.
    _add_cn_monthly(s["cn_b"], s["month"], s["year"], AppraisalStatus.LOCKED)
    lider_b_row = _add_quarter_bonuses(
        s["ev_b"], s["cn_b"], s["lider_b"], s["quarter"], s["year"],
        leadership_status=AppraisalStatus.REVOPS_REVIEW,
    )
    db.session.flush()

    appraisal = Appraisal(
        month=s["month"], year=s["year"],
        status=AppraisalStatus.REVOPS_REVIEW,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()
    transition_appraisal(
        appraisal, AppraisalStatus.LOCKED, approved_by=s["admin"].id,
    )

    db.session.refresh(s["cycle"])
    assert s["cycle"].status == MonthlyCycleStatus.OPEN

    transition_lider_vendas_appraisal(lider_b_row, AppraisalStatus.LOCKED)
    db.session.flush()

    db.session.refresh(s["cycle"])
    assert s["cycle"].status == MonthlyCycleStatus.LOCKED


def test_ev_apuracao_component_exposes_appraisal_id(db_session, two_teams_setup):
    s = two_teams_setup
    appraisal = Appraisal(
        month=s["month"], year=s["year"],
        status=AppraisalStatus.DRAFT,
        created_by=s["admin"].id,
    )
    db.session.add(appraisal)
    db.session.flush()

    comp = build_cycle_payload(s["cycle"])["components"]["ev_apuracao"]
    assert comp["status"] == "DRAFT"
    assert comp["appraisal_id"] == str(appraisal.id)


def test_ev_apuracao_component_pending_without_appraisal(
    db_session, two_teams_setup,
):
    s = two_teams_setup
    comp = build_cycle_payload(s["cycle"])["components"]["ev_apuracao"]
    assert comp["status"] == "PENDING"
    assert comp["appraisal_id"] is None
    assert comp["validations_total"] == 0


def test_leadership_component_exposes_single_row_id(db_session, two_teams_setup):
    s = two_teams_setup
    row = LiderVendasQuarterAppraisal(
        lider_vendas_id=s["lider_a"].id, quarter=s["quarter"], year=s["year"],
        meta_mrr=Decimal("100000"), meta_sql=10,
        realizado_mrr=Decimal("100000"), realizado_sql=10,
        pct_mrr=Decimal("1.0"), pct_sql=Decimal("1.0"),
        multiplicador=Decimal("2.0"), bonus_amount=Decimal("16000"),
        status=AppraisalStatus.REVOPS_REVIEW,
    )
    db.session.add(row)
    db.session.flush()

    comp = build_cycle_payload(s["cycle"])["components"]["leadership_bonus"]
    assert comp["status"] == "REVOPS_REVIEW"
    assert comp["appraisal_id"] == str(row.id)
    assert comp["rows"] == 1
    assert comp["expected"] == 2  # fixture has 2 active LIDER_VENDAS


def test_bonus_component_incomplete_final_set_stays_calculating(
    db_session, two_teams_setup,
):
    """All-final bonus rows that miss an eligible user must not read LOCKED."""
    s = two_teams_setup
    db.session.add(EvQuarterAchievement(
        ev_id=s["ev_a"].id, quarter=s["quarter"], year=s["year"],
        total_mrr=Decimal("100000"), mrr_target=Decimal("100000"),
        achievement_pct=Decimal("1.0"), is_final=True,
    ))
    db.session.flush()

    comp = build_cycle_payload(s["cycle"])["components"]["ev_bonus"]
    assert comp["rows"] == 1
    assert comp["final"] == 1
    assert comp["expected"] == 2  # ev_a + ev_b
    assert comp["status"] == "CALCULATING"


def test_leadership_component_multiple_rows_has_no_appraisal_id(
    db_session, two_teams_setup,
):
    """With 2+ leadership rows the inline-action id is ambiguous → None."""
    s = two_teams_setup
    for lider in (s["lider_a"], s["lider_b"]):
        db.session.add(LiderVendasQuarterAppraisal(
            lider_vendas_id=lider.id, quarter=s["quarter"], year=s["year"],
            meta_mrr=Decimal("100000"), meta_sql=10,
            realizado_mrr=Decimal("100000"), realizado_sql=10,
            pct_mrr=Decimal("1.0"), pct_sql=Decimal("1.0"),
            multiplicador=Decimal("2.0"), bonus_amount=Decimal("16000"),
            status=AppraisalStatus.VALIDATING,
        ))
    db.session.flush()

    comp = build_cycle_payload(s["cycle"])["components"]["leadership_bonus"]
    assert comp["rows"] == 2
    assert comp["appraisal_id"] is None


def test_locked_cycle_components_skip_expected_guard(
    db_session, two_teams_setup,
):
    """A LOCKED cycle is frozen history: a hire after the lock must not
    downgrade its components to CALCULATING."""
    s = two_teams_setup
    cycle = MonthlyCycle(
        month=5, year=s["year"],
        status=MonthlyCycleStatus.LOCKED,
        created_by=s["admin"].id,
    )
    db.session.add(cycle)
    # Only one of the two active CNs has a (LOCKED) row.
    _add_cn_monthly(s["cn_a"], 5, s["year"], AppraisalStatus.LOCKED)
    db.session.flush()

    comp = build_cycle_payload(cycle)["components"]["cn_apuracao"]
    assert comp["rows"] == 1
    assert comp["expected"] == 2
    assert comp["status"] == "LOCKED"
