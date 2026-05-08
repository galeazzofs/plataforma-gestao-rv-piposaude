"""Endpoint tests for CN monthly appraisal transitions (issue #34)."""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    AppraisalStatus, CnMonthlyAppraisal, User, UserRole,
)
from app.auth.jwt_manager import create_access_token


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def cn_appraisal_setup():
    """One ADMIN, one CN, one LIDER_VENDAS, one CnMonthlyAppraisal in CALCULATING."""
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"tx-admin-{suffix}@x", name="TX Admin",
                 role=UserRole.ADMIN, active=True)
    cn = User(email=f"tx-cn-{suffix}@x", name="TX CN",
              role=UserRole.CN, active=True, salario_base=Decimal("8000"))
    lider = User(email=f"tx-lider-{suffix}@x", name="TX Lider",
                 role=UserRole.LIDER_VENDAS, active=True)
    db.session.add_all([admin, cn, lider])
    db.session.flush()

    a = CnMonthlyAppraisal(
        cn_id=cn.id, month=11, year=2032,
        sao_realizado=Decimal("0"), vidas_realizado=Decimal("0"),
        pct_sao=Decimal("0"), pct_vidas=Decimal("0"),
        score_final=Decimal("0"), multiplicador=Decimal("0"),
        commission_amount=Decimal("0"),
        status=AppraisalStatus.CALCULATING,
    )
    db.session.add(a)
    db.session.commit()

    yield {"admin": admin, "cn": cn, "lider": lider, "appraisal": a}

    db.session.delete(a)
    db.session.delete(cn)
    db.session.delete(lider)
    db.session.delete(admin)
    db.session.commit()


def _transition(client, appraisal_id, to_status, user):
    return client.post(
        f"/api/v1/commissions/cn/appraisal/{appraisal_id}/transition",
        json={"to": to_status},
        headers=_auth(user),
    )


def test_admin_can_transition_to_validating(client, cn_appraisal_setup):
    s = cn_appraisal_setup
    resp = _transition(client, s["appraisal"].id, "VALIDATING", s["admin"])
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "VALIDATING"


def test_cn_can_send_own_validating_to_lider_review(client, cn_appraisal_setup):
    s = cn_appraisal_setup
    _transition(client, s["appraisal"].id, "VALIDATING", s["admin"])
    resp = _transition(client, s["appraisal"].id, "LIDER_REVIEW", s["cn"])
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "LIDER_REVIEW"


def test_cn_cannot_skip_to_locked(client, cn_appraisal_setup):
    s = cn_appraisal_setup
    _transition(client, s["appraisal"].id, "VALIDATING", s["admin"])
    resp = _transition(client, s["appraisal"].id, "LOCKED", s["cn"])
    assert resp.status_code == 403


def test_lider_can_send_lider_review_to_revops_review(client, cn_appraisal_setup):
    s = cn_appraisal_setup
    _transition(client, s["appraisal"].id, "VALIDATING", s["admin"])
    _transition(client, s["appraisal"].id, "LIDER_REVIEW", s["admin"])
    resp = _transition(client, s["appraisal"].id, "REVOPS_REVIEW", s["lider"])
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "REVOPS_REVIEW"


def test_invalid_target_returns_422(client, cn_appraisal_setup):
    s = cn_appraisal_setup
    # CALCULATING → LOCKED is not a valid one-step transition
    resp = _transition(client, s["appraisal"].id, "LOCKED", s["admin"])
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "INVALID_TRANSITION"
