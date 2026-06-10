"""Tests for POST /commissions/ev/bonus/finalize."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal, CnQuarterBonus,
    EvQuarterAchievement, LiderVendasQuarterAppraisal,
    MonthlyCycle, MonthlyCycleStatus,
    User, UserRole,
)
from app.auth.jwt_manager import create_access_token

QUARTER, YEAR = 2, 2033


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _make_user(role, name):
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"{name.lower()}-{suffix}@x", name=name, role=role,
        active=True, salario_base=Decimal("8000"),
    )
    db.session.add(u)
    db.session.flush()
    return u


def _add_achievement(ev, is_final=False):
    row = EvQuarterAchievement(
        ev_id=ev.id, quarter=QUARTER, year=YEAR,
        total_mrr=Decimal("100000"), mrr_target=Decimal("100000"),
        achievement_pct=Decimal("1.0"), is_final=is_final,
    )
    db.session.add(row)
    db.session.flush()
    return row


@pytest.fixture
def setup():
    return {
        "admin": _make_user(UserRole.ADMIN, "EvFinAdmin"),
        "ev_a": _make_user(UserRole.EV, "EvFinA"),
        "ev_b": _make_user(UserRole.EV, "EvFinB"),
    }


def test_finalize_locks_all_non_final_rows(client, setup):
    s = setup
    row_a = _add_achievement(s["ev_a"])
    row_b = _add_achievement(s["ev_b"], is_final=True)

    resp = client.post(
        "/api/v1/commissions/ev/bonus/finalize",
        json={"quarter": QUARTER, "year": YEAR},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["finalized"] == 1
    db.session.refresh(row_a)
    db.session.refresh(row_b)
    assert row_a.is_final is True
    assert row_b.is_final is True


def test_finalize_validates_body(client, setup):
    resp = client.post(
        "/api/v1/commissions/ev/bonus/finalize",
        json={"quarter": "x"},
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 400


def test_finalize_requires_admin(client, setup):
    resp = client.post(
        "/api/v1/commissions/ev/bonus/finalize",
        json={"quarter": QUARTER, "year": YEAR},
        headers=_auth_header(setup["ev_a"]),
    )
    assert resp.status_code == 403


def test_finalize_computes_missing_amounts_before_locking(client, setup):
    """Achievement rows created by the achievements editor pre-exist the
    bonus run with bonus_amount=NULL. Finalize must never lock a NULL —
    it runs the bonus calculator first (compute-then-lock)."""
    s = setup
    row = _add_achievement(s["ev_a"])  # bonus_amount is NULL here

    resp = client.post(
        "/api/v1/commissions/ev/bonus/finalize",
        json={"quarter": QUARTER, "year": YEAR},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    db.session.refresh(row)
    assert row.is_final is True
    assert row.bonus_amount is not None


def test_finalize_rejects_quarter_out_of_range(client, setup):
    resp = client.post(
        "/api/v1/commissions/ev/bonus/finalize",
        json={"quarter": 7, "year": YEAR},
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 400


def test_finalize_triggers_quarter_end_cycle_autolock(client, setup):
    """Quarter-end month cycle (month=6, Q2) auto-locks once ev_bonus
    finalize locks the last remaining non-final component.

    Setup: 1 EV, 1 CN, 1 LIDER_VENDAS, each with exactly one row so
    `expected` == `rows` for every component. The EV achievement is the
    only non-final row; after finalize the cycle must be LOCKED."""
    s = setup
    # Use a year that won't collide with YEAR from other tests.
    year = YEAR + 1
    quarter = 2
    month = quarter * 3  # = 6

    # Create users that will be the sole active members of their roles.
    # NOTE: the `setup` fixture already creates ev_a and ev_b (both active
    # EV), so we cannot reuse them here — the aggregator's `expected` count
    # would be 2 while we only supply 1 row, holding the component open.
    # We mark those fixture EVs as inactive for this test so they don't
    # count toward `expected`, then create one dedicated active EV.
    s["ev_a"].active = False
    s["ev_b"].active = False
    db.session.flush()

    ev = _make_user(UserRole.EV, "EvFinAutoLockEV")
    cn = _make_user(UserRole.CN, "EvFinCN")
    lider = _make_user(UserRole.LIDER_VENDAS, "EvFinLider")

    cycle = MonthlyCycle(
        month=month, year=year,
        status=MonthlyCycleStatus.OPEN,
        created_by=s["admin"].id,
    )
    db.session.add(cycle)

    # ev_apuracao: LOCKED Appraisal
    db.session.add(Appraisal(
        month=month, year=year,
        status=AppraisalStatus.LOCKED,
        created_by=s["admin"].id,
    ))

    # cn_apuracao: LOCKED CnMonthlyAppraisal
    db.session.add(CnMonthlyAppraisal(
        cn_id=cn.id, month=month, year=year,
        sao_realizado=Decimal("100"), vidas_realizado=Decimal("10"),
        pct_sao=Decimal("1.0"), pct_vidas=Decimal("1.0"),
        score_final=Decimal("1.0"), multiplicador=Decimal("1.0"),
        commission_amount=Decimal("0"),
        status=AppraisalStatus.LOCKED,
    ))

    # cn_bonus: final CnQuarterBonus
    db.session.add(CnQuarterBonus(
        cn_id=cn.id, quarter=quarter, year=year,
        sao_trim_realizado=Decimal("100"), sao_trim_meta=Decimal("100"),
        pct_sao_trim=Decimal("1.0"), multiplicador=Decimal("1.0"),
        bonus_amount=Decimal("8000"), is_final=True,
    ))

    # leadership_bonus: LOCKED LiderVendasQuarterAppraisal
    db.session.add(LiderVendasQuarterAppraisal(
        lider_vendas_id=lider.id, quarter=quarter, year=year,
        meta_mrr=Decimal("100000"), meta_sql=10,
        realizado_mrr=Decimal("100000"), realizado_sql=10,
        pct_mrr=Decimal("1.0"), pct_sql=Decimal("1.0"),
        multiplicador=Decimal("2.0"), bonus_amount=Decimal("16000"),
        status=AppraisalStatus.LOCKED,
    ))

    # ev_bonus: NON-final EvQuarterAchievement (the blocker)
    ach = EvQuarterAchievement(
        ev_id=ev.id, quarter=quarter, year=year,
        total_mrr=Decimal("100000"), mrr_target=Decimal("100000"),
        achievement_pct=Decimal("1.0"), is_final=False,
    )
    db.session.add(ach)
    db.session.flush()

    resp = client.post(
        "/api/v1/commissions/ev/bonus/finalize",
        json={"quarter": quarter, "year": year},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200

    db.session.refresh(cycle)
    assert cycle.status == MonthlyCycleStatus.LOCKED, (
        f"Expected cycle LOCKED but got {cycle.status}"
    )
