"""Tests for POST /commissions/ev/bonus/finalize."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import EvQuarterAchievement, User, UserRole
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
