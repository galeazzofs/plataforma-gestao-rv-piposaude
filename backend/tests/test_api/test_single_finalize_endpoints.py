"""Mid-chain regression tests for the single-row finalize endpoints.

POST /commissions/cn/appraisal/<id>/finalize and
POST /commissions/leadership/appraisal/<id>/finalize walk the state
machine to LOCKED. The naive walk ("skip the step equal to the current
status") attempts BACKWARD transitions for rows already past VALIDATING
(e.g. REVOPS_REVIEW -> VALIDATING), which the state machine rejects —
the endpoints must apply only the steps after the row's position.
"""
from decimal import Decimal
import uuid

import pytest

from app.extensions import db
from app.models import (
    AppraisalStatus, CnMonthlyAppraisal, LiderVendasQuarterAppraisal,
    User, UserRole,
)
from app.auth.jwt_manager import create_access_token

MONTH, YEAR, QUARTER = 5, 2034, 2


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


def _add_cn_row(cn_user, status):
    row = CnMonthlyAppraisal(
        cn_id=cn_user.id, month=MONTH, year=YEAR,
        sao_realizado=Decimal("100"), vidas_realizado=Decimal("10"),
        pct_sao=Decimal("1.0"), pct_vidas=Decimal("1.0"),
        score_final=Decimal("1.0"), multiplicador=Decimal("1.0"),
        commission_amount=Decimal("0"), status=status,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _add_leadership_row(lider, status):
    row = LiderVendasQuarterAppraisal(
        lider_vendas_id=lider.id, quarter=QUARTER, year=YEAR,
        meta_mrr=Decimal("100000"), meta_sql=10,
        realizado_mrr=Decimal("100000"), realizado_sql=10,
        pct_mrr=Decimal("1.0"), pct_sql=Decimal("1.0"),
        multiplicador=Decimal("2.0"), bonus_amount=Decimal("16000"),
        status=status,
    )
    db.session.add(row)
    db.session.flush()
    return row


@pytest.fixture
def setup():
    return {
        "admin": _make_user(UserRole.ADMIN, "FinAdmin"),
        "cn": _make_user(UserRole.CN, "FinCn"),
        "lider": _make_user(UserRole.LIDER_VENDAS, "FinLider"),
    }


@pytest.mark.parametrize("start_status", [
    AppraisalStatus.LIDER_REVIEW,
    AppraisalStatus.REVOPS_REVIEW,
])
def test_cn_finalize_from_mid_chain(client, setup, start_status):
    row = _add_cn_row(setup["cn"], start_status)

    resp = client.post(
        f"/api/v1/commissions/cn/appraisal/{row.id}/finalize",
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 200
    db.session.refresh(row)
    assert row.status == AppraisalStatus.LOCKED


def test_cn_finalize_from_calculating_walks_full_chain(client, setup):
    row = _add_cn_row(setup["cn"], AppraisalStatus.CALCULATING)

    resp = client.post(
        f"/api/v1/commissions/cn/appraisal/{row.id}/finalize",
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 200
    db.session.refresh(row)
    assert row.status == AppraisalStatus.LOCKED


@pytest.mark.parametrize("start_status", [
    AppraisalStatus.LIDER_REVIEW,
    AppraisalStatus.REVOPS_REVIEW,
])
def test_leadership_finalize_from_mid_chain(client, setup, start_status):
    row = _add_leadership_row(setup["lider"], start_status)

    resp = client.post(
        f"/api/v1/commissions/leadership/appraisal/{row.id}/finalize",
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 200
    db.session.refresh(row)
    assert row.status == AppraisalStatus.LOCKED


def test_leadership_finalize_already_locked_conflicts(client, setup):
    row = _add_leadership_row(setup["lider"], AppraisalStatus.LOCKED)

    resp = client.post(
        f"/api/v1/commissions/leadership/appraisal/{row.id}/finalize",
        headers=_auth_header(setup["admin"]),
    )
    assert resp.status_code == 409
