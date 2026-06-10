"""Tests for the month-level bulk CN appraisal actions
(POST /commissions/cn/appraisal/transition-month and /finalize-month)."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, CnMonthlyAppraisal,
    MonthlyCycle, MonthlyCycleStatus, User, UserRole,
)
from app.auth.jwt_manager import create_access_token

MONTH, YEAR = 5, 2033


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


def _add_cn_row(cn_user, status, contested=False):
    row = CnMonthlyAppraisal(
        cn_id=cn_user.id, month=MONTH, year=YEAR,
        sao_realizado=Decimal("100"), vidas_realizado=Decimal("10"),
        pct_sao=Decimal("1.0"), pct_vidas=Decimal("1.0"),
        score_final=Decimal("1.0"), multiplicador=Decimal("1.0"),
        commission_amount=Decimal("0"), status=status,
        has_contestation=contested,
    )
    db.session.add(row)
    db.session.flush()
    return row


@pytest.fixture
def setup():
    admin = _make_user(UserRole.ADMIN, "BulkAdmin")
    cn_a = _make_user(UserRole.CN, "BulkCnA")
    cn_b = _make_user(UserRole.CN, "BulkCnB")
    return {"admin": admin, "cn_a": cn_a, "cn_b": cn_b}


def test_transition_month_advances_all_rows(client, setup):
    s = setup
    _add_cn_row(s["cn_a"], AppraisalStatus.CALCULATING)
    _add_cn_row(s["cn_b"], AppraisalStatus.CALCULATING)

    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": MONTH, "year": YEAR, "to": "VALIDATING"},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["advanced"] == 2
    assert data["skipped"] == []
    statuses = {
        r.status for r in CnMonthlyAppraisal.query.filter_by(
            month=MONTH, year=YEAR,
        ).all()
    }
    assert statuses == {AppraisalStatus.VALIDATING}


def test_transition_month_is_idempotent(client, setup):
    s = setup
    _add_cn_row(s["cn_a"], AppraisalStatus.CALCULATING)

    for expected_advanced in (1, 0):
        resp = client.post(
            "/api/v1/commissions/cn/appraisal/transition-month",
            json={"month": MONTH, "year": YEAR, "to": "VALIDATING"},
            headers=_auth_header(s["admin"]),
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["advanced"] == expected_advanced


def test_transition_month_skips_contested_rows(client, setup):
    s = setup
    _add_cn_row(s["cn_a"], AppraisalStatus.VALIDATING)
    contested = _add_cn_row(
        s["cn_b"], AppraisalStatus.VALIDATING, contested=True,
    )

    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": MONTH, "year": YEAR, "to": "LIDER_REVIEW"},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["advanced"] == 1
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["cn_id"] == str(s["cn_b"].id)
    db.session.refresh(contested)
    assert contested.status == AppraisalStatus.VALIDATING


def test_transition_month_404_without_rows(client, setup):
    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": 11, "year": 2099, "to": "VALIDATING"},
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 404


def test_transition_month_validates_body(client, setup):
    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": MONTH, "year": YEAR, "to": "NOT_A_STATUS"},
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 400


def test_transition_month_requires_admin(client, setup):
    cn = setup["cn_a"]
    resp = client.post(
        "/api/v1/commissions/cn/appraisal/transition-month",
        json={"month": MONTH, "year": YEAR, "to": "VALIDATING"},
        headers=_auth_header(cn),
    )
    assert resp.status_code == 403


def test_finalize_month_locks_all_and_skips_contested(client, setup):
    s = setup
    clean = _add_cn_row(s["cn_a"], AppraisalStatus.REVOPS_REVIEW)
    contested = _add_cn_row(
        s["cn_b"], AppraisalStatus.REVOPS_REVIEW, contested=True,
    )

    resp = client.post(
        "/api/v1/commissions/cn/appraisal/finalize-month",
        json={"month": MONTH, "year": YEAR},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["advanced"] == 1
    assert len(data["skipped"]) == 1
    db.session.refresh(clean)
    db.session.refresh(contested)
    assert clean.status == AppraisalStatus.LOCKED
    assert contested.status == AppraisalStatus.REVOPS_REVIEW


def test_finalize_month_triggers_cycle_autolock(client, setup):
    """Locking the last CN row must re-evaluate the month's cycle."""
    s = setup
    cycle = MonthlyCycle(
        month=MONTH, year=YEAR,
        status=MonthlyCycleStatus.OPEN, created_by=s["admin"].id,
    )
    db.session.add(cycle)
    # Apuração EV already LOCKED — the CN rows are the last gate.
    db.session.add(Appraisal(
        month=MONTH, year=YEAR,
        status=AppraisalStatus.LOCKED, created_by=s["admin"].id,
    ))
    _add_cn_row(s["cn_a"], AppraisalStatus.REVOPS_REVIEW)
    _add_cn_row(s["cn_b"], AppraisalStatus.REVOPS_REVIEW)
    db.session.flush()

    resp = client.post(
        "/api/v1/commissions/cn/appraisal/finalize-month",
        json={"month": MONTH, "year": YEAR},
        headers=_auth_header(s["admin"]),
    )
    assert resp.status_code == 200
    db.session.refresh(cycle)
    assert cycle.status == MonthlyCycleStatus.LOCKED


def test_finalize_month_requires_admin(client, setup):
    resp = client.post(
        "/api/v1/commissions/cn/appraisal/finalize-month",
        json={"month": MONTH, "year": YEAR},
        headers=_auth_header(setup["cn_a"]),
    )
    assert resp.status_code == 403
