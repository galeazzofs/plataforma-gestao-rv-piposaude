"""Tests for /api/v1/commissions/cn/quarterly-bonus endpoints (issue #33)."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    AppraisalStatus, User, UserRole, CnMonthlyGoal, CnMonthlyAppraisal,
    CnQuarterBonus,
)
from app.auth.jwt_manager import create_access_token


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def cn_quarter_setup():
    """One admin, one CN with the 3 final monthly appraisals for Q4/2030.

    Cleans up everything in teardown so committed data from the API
    endpoints does not leak into other tests in the suite.
    """
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"qb-admin-{suffix}@x", name="QB Admin",
                 role=UserRole.ADMIN, active=True)
    cn = User(email=f"qb-cn-{suffix}@x", name="QB CN",
              role=UserRole.CN, active=True, salario_base=Decimal("8000"))
    db.session.add_all([admin, cn])
    db.session.flush()

    goals = []
    appraisals = []
    for m in (10, 11, 12):
        g = CnMonthlyGoal(
            cn_id=cn.id, month=m, year=2030,
            sao_target=Decimal("100"), vidas_target=Decimal("10"),
        )
        a = CnMonthlyAppraisal(
            cn_id=cn.id, month=m, year=2030,
            sao_realizado=Decimal("110"), vidas_realizado=Decimal("8"),
            pct_sao=Decimal("1.0"), pct_vidas=Decimal("0.8"),
            score_final=Decimal("0.9"), multiplicador=Decimal("1.0"),
            commission_amount=Decimal("0"), status=AppraisalStatus.LOCKED,
        )
        db.session.add_all([g, a])
        goals.append(g)
        appraisals.append(a)
    db.session.commit()

    yield {"admin": admin, "cn": cn, "quarter": 4, "year": 2030}

    # Teardown — the API commits, so we must clean up explicitly.
    CnQuarterBonus.query.filter_by(cn_id=cn.id).delete()
    for a in appraisals:
        db.session.delete(a)
    for g in goals:
        db.session.delete(g)
    db.session.delete(cn)
    db.session.delete(admin)
    db.session.commit()


def test_run_endpoint_creates_bonus(client, cn_quarter_setup):
    s = cn_quarter_setup
    resp = client.post(
        "/api/v1/commissions/cn/quarterly-bonus",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["admin"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["bonuses_computed"] >= 1

    bonus = CnQuarterBonus.query.filter_by(
        cn_id=s["cn"].id, quarter=s["quarter"], year=s["year"],
    ).first()
    assert bonus is not None
    assert bonus.bonus_amount == Decimal("8000.00")


def test_run_endpoint_requires_admin(client, cn_quarter_setup):
    s = cn_quarter_setup
    resp = client.post(
        "/api/v1/commissions/cn/quarterly-bonus",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["cn"]),
    )
    assert resp.status_code == 403


def test_list_endpoint_filters_by_quarter_year(client, cn_quarter_setup):
    s = cn_quarter_setup
    client.post(
        "/api/v1/commissions/cn/quarterly-bonus",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["admin"]),
    )

    resp = client.get(
        f"/api/v1/commissions/cn/quarterly-bonus"
        f"?quarter={s['quarter']}&year={s['year']}",
        headers=_auth(s["admin"]),
    )
    assert resp.status_code == 200
    items = resp.get_json()["data"]
    assert any(i["cn_id"] == str(s["cn"].id) for i in items)


def test_list_endpoint_cn_only_sees_self(client, cn_quarter_setup):
    s = cn_quarter_setup
    client.post(
        "/api/v1/commissions/cn/quarterly-bonus",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["admin"]),
    )
    resp = client.get(
        f"/api/v1/commissions/cn/quarterly-bonus"
        f"?quarter={s['quarter']}&year={s['year']}",
        headers=_auth(s["cn"]),
    )
    assert resp.status_code == 200
    items = resp.get_json()["data"]
    cn_ids = {i["cn_id"] for i in items}
    assert cn_ids == {str(s["cn"].id)}


def test_finalize_endpoint_locks_bonuses(client, cn_quarter_setup):
    s = cn_quarter_setup
    client.post(
        "/api/v1/commissions/cn/quarterly-bonus",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["admin"]),
    )

    resp = client.post(
        "/api/v1/commissions/cn/quarterly-bonus/finalize",
        json={"quarter": s["quarter"], "year": s["year"]},
        headers=_auth(s["admin"]),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["finalized"] >= 1

    bonus = CnQuarterBonus.query.filter_by(
        cn_id=s["cn"].id, quarter=s["quarter"], year=s["year"],
    ).first()
    assert bonus.is_final is True


def test_run_endpoint_invalid_quarter(client, cn_quarter_setup):
    resp = client.post(
        "/api/v1/commissions/cn/quarterly-bonus",
        json={"quarter": 7, "year": 2030},
        headers=_auth(cn_quarter_setup["admin"]),
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
