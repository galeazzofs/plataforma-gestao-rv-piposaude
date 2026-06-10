"""Tests for the CN goals coverage endpoint
(GET /commissions/cn/goals/coverage).

Coverage mirrors validate_cn_goals(): a CN "has a goal" for a month when
the CnMonthlyGoal row exists, regardless of the sao_target value.
"""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import CnMonthlyGoal, User, UserRole
from app.auth.jwt_manager import create_access_token

YEAR = 2031


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _make_user(role, name, active=True):
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"{name.lower()}-{suffix}@x", name=name, role=role,
        active=active, salario_base=Decimal("8000"),
    )
    db.session.add(u)
    db.session.flush()
    return u


def _add_goal(cn_user, month, sao="100"):
    goal = CnMonthlyGoal(
        cn_id=cn_user.id, month=month, year=YEAR,
        sao_target=Decimal(sao), vidas_target=Decimal("0"),
    )
    db.session.add(goal)
    db.session.flush()
    return goal


@pytest.fixture
def setup():
    admin = _make_user(UserRole.ADMIN, "CovAdmin")
    cn_a = _make_user(UserRole.CN, "CovCnA")
    cn_b = _make_user(UserRole.CN, "CovCnB")
    cn_c = _make_user(UserRole.CN, "CovCnC")
    cn_off = _make_user(UserRole.CN, "CovCnOff", active=False)
    return {"admin": admin, "cn_a": cn_a, "cn_b": cn_b,
            "cn_c": cn_c, "cn_off": cn_off}


def test_coverage_requires_admin(client, setup):
    resp = client.get(
        f"/api/v1/commissions/cn/goals/coverage?year={YEAR}",
        headers=_auth_header(setup["cn_a"]),
    )
    assert resp.status_code == 403


def test_coverage_requires_year(client, setup):
    resp = client.get(
        "/api/v1/commissions/cn/goals/coverage",
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 400


def test_coverage_counts_goal_rows_per_month(client, setup):
    s = setup
    _add_goal(s["cn_a"], 5)
    # sao 0 still counts: validate_cn_goals only checks row existence.
    _add_goal(s["cn_b"], 5, sao="0")
    _add_goal(s["cn_a"], 6)
    # Goals of inactive CNs are invisible to the apuração; don't count them.
    _add_goal(s["cn_off"], 5)

    resp = client.get(
        f"/api/v1/commissions/cn/goals/coverage?year={YEAR}",
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    # cn_off is inactive: 3 active CNs (a, b, c) at minimum. Other tests in
    # the session may add active CNs, but inside this transaction-isolated
    # test only ours exist.
    assert data["active_cns"] == 3
    months = data["months"]
    assert months["5"] == 2
    assert months["6"] == 1
    # All 12 months are present, zero-filled.
    assert set(months.keys()) == {str(m) for m in range(1, 13)}
    assert months["1"] == 0
    assert months["12"] == 0
