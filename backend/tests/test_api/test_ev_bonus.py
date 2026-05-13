"""Tests for /api/v1/commissions/ev/bonus endpoints."""
from decimal import Decimal
import uuid

import pytest

from app.auth.jwt_manager import create_access_token
from app.extensions import db
from app.models import EvQuarterAchievement, User, UserRole


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ev_bonus_setup():
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"evb-admin-{suffix}@x", name="EVB Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"evb-ev-{suffix}@x", name="EV Bonus",
              role=UserRole.EV, active=True, salario_base=Decimal("6000"))
    other_ev = User(email=f"evb-other-{suffix}@x", name="Other EV",
                    role=UserRole.EV, active=True, salario_base=Decimal("5000"))
    db.session.add_all([admin, ev, other_ev])
    db.session.flush()

    achievement = EvQuarterAchievement(
        ev_id=ev.id,
        quarter=4,
        year=2030,
        total_mrr=Decimal("100000"),
        mrr_target=Decimal("100000"),
        achievement_pct=Decimal("1.0000"),
        is_final=False,
    )
    other_achievement = EvQuarterAchievement(
        ev_id=other_ev.id,
        quarter=4,
        year=2030,
        total_mrr=Decimal("50000"),
        mrr_target=Decimal("100000"),
        achievement_pct=Decimal("0.5000"),
        is_final=False,
    )
    db.session.add_all([achievement, other_achievement])
    db.session.commit()

    yield {"admin": admin, "ev": ev, "other_ev": other_ev,
           "quarter": 4, "year": 2030}

    EvQuarterAchievement.query.filter(
        EvQuarterAchievement.ev_id.in_([ev.id, other_ev.id])
    ).delete(synchronize_session=False)
    db.session.delete(ev)
    db.session.delete(other_ev)
    db.session.delete(admin)
    db.session.commit()


def test_run_endpoint_creates_ev_bonus(client, ev_bonus_setup):
    s = ev_bonus_setup

    resp = client.post(
        "/api/v1/commissions/ev/bonus",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["admin"]),
    )

    assert resp.status_code == 200
    assert resp.get_json()["data"]["bonuses_computed"] == 2

    achievement = EvQuarterAchievement.query.filter_by(
        ev_id=s["ev"].id, quarter=s["quarter"], year=s["year"],
    ).first()
    assert achievement.bonus_amount == Decimal("6000.00")
    assert achievement.salario_base_snapshot == Decimal("6000.00")


def test_run_endpoint_requires_admin(client, ev_bonus_setup):
    s = ev_bonus_setup

    resp = client.post(
        "/api/v1/commissions/ev/bonus",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["ev"]),
    )

    assert resp.status_code == 403


def test_list_endpoint_filters_and_includes_ev_name(client, ev_bonus_setup):
    s = ev_bonus_setup
    client.post(
        "/api/v1/commissions/ev/bonus",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["admin"]),
    )

    resp = client.get(
        f"/api/v1/commissions/ev/bonus?quarter={s['quarter']}&year={s['year']}",
        headers=_auth(s["admin"]),
    )

    assert resp.status_code == 200
    items = resp.get_json()["data"]
    ev_row = next(i for i in items if i["ev_id"] == str(s["ev"].id))
    assert ev_row["ev_name"] == "EV Bonus"
    assert ev_row["bonus_amount"] == "6000.00"


def test_list_endpoint_ev_only_sees_self(client, ev_bonus_setup):
    s = ev_bonus_setup
    client.post(
        "/api/v1/commissions/ev/bonus",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["admin"]),
    )

    resp = client.get(
        f"/api/v1/commissions/ev/bonus?quarter={s['quarter']}&year={s['year']}",
        headers=_auth(s["ev"]),
    )

    assert resp.status_code == 200
    ev_ids = {i["ev_id"] for i in resp.get_json()["data"]}
    assert ev_ids == {str(s["ev"].id)}


def test_run_endpoint_invalid_quarter(client, ev_bonus_setup):
    resp = client.post(
        "/api/v1/commissions/ev/bonus",
        json={"quarter": 7, "year": ev_bonus_setup["year"]},
        headers=_auth(ev_bonus_setup["admin"]),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_endpoint_invalid_quarter(client, ev_bonus_setup):
    resp = client.get(
        "/api/v1/commissions/ev/bonus?quarter=7&year=2030",
        headers=_auth(ev_bonus_setup["admin"]),
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
