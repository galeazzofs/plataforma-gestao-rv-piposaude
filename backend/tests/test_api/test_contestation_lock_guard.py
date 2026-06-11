"""Contestation is BLOCKING: no row reaches LOCKED with an open contestation,
in any domain (EV appraisal, CN monthly, leadership quarterly), through any
path (transition endpoint, single-row finalize); and a contestation can only
be resolved while the row is in REVOPS_REVIEW — resolving a LOCKED row used
to corrupt state (LOCKED → VALIDATING by direct write, locked_at intact).
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, Appraisal, AppraisalStatus,
    CnMonthlyAppraisal, LiderVendasQuarterAppraisal,
)
from app.auth.jwt_manager import create_access_token
from app.modules.workflow.state_machine import (
    transition_lider_vendas_appraisal, InvalidTransitionError,
)


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def users():
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"adm-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    cn = User(email=f"cn-{suffix}@x", name="CN", role=UserRole.CN, active=True)
    lider = User(email=f"lid-{suffix}@x", name="Lider",
                 role=UserRole.LIDER_VENDAS, active=True)
    db.session.add_all([admin, cn, lider])
    db.session.commit()
    return {"admin": admin, "cn": cn, "lider": lider}


def _ev_appraisal(users, status, contested=True):
    a = Appraisal(month=7, year=2026, status=status,
                  created_by=users["admin"].id,
                  has_contestation=contested,
                  contestation_note="valores errados" if contested else None)
    if status == AppraisalStatus.LOCKED:
        a.locked_at = datetime.now(timezone.utc)
    db.session.add(a)
    db.session.commit()
    return a


def _cn_appraisal(users, status, contested=True):
    a = CnMonthlyAppraisal(
        cn_id=users["cn"].id, month=7, year=2026, status=status,
        sao_realizado=Decimal("10"), vidas_realizado=Decimal("120"),
        pct_sao=Decimal("1.0"), pct_vidas=Decimal("1.0"),
        score_final=Decimal("1.0"), multiplicador=Decimal("1.0"),
        commission_amount=Decimal("500.00"),
        has_contestation=contested,
        contestation_note="conta errada" if contested else None,
    )
    db.session.add(a)
    db.session.commit()
    return a


# ── EV appraisal ──────────────────────────────────────────────────────


def test_ev_lock_blocked_with_open_contestation(client, db_session, users):
    a = _ev_appraisal(users, AppraisalStatus.REVOPS_REVIEW)
    resp = client.post(
        f"/api/v1/appraisals/{a.id}/transition", json={"to": "LOCKED"},
        headers=_auth_header(users["admin"]),
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "INVALID_TRANSITION"
    db.session.refresh(a)
    assert a.status == AppraisalStatus.REVOPS_REVIEW
    assert a.locked_at is None


def test_ev_lock_passes_after_resolution(client, db_session, users):
    a = _ev_appraisal(users, AppraisalStatus.REVOPS_REVIEW)
    headers = _auth_header(users["admin"])

    resp = client.post(
        f"/api/v1/appraisals/{a.id}/resolve-contestation",
        json={"resolution_note": "ajustado"}, headers=headers,
    )
    assert resp.status_code == 200
    db.session.refresh(a)
    assert a.has_contestation is False
    assert a.status == AppraisalStatus.VALIDATING

    # Re-validation loop completes and the lock now goes through.
    resp = client.post(
        f"/api/v1/appraisals/{a.id}/transition",
        json={"to": "REVOPS_REVIEW"}, headers=headers,
    )
    assert resp.status_code == 200
    resp = client.post(
        f"/api/v1/appraisals/{a.id}/transition",
        json={"to": "LOCKED"}, headers=headers,
    )
    assert resp.status_code == 200
    db.session.refresh(a)
    assert a.status == AppraisalStatus.LOCKED


def test_ev_resolve_rejected_after_lock(client, db_session, users):
    """A LOCKED row with a (legacy) open contestation must not be torn back
    to VALIDATING by the resolve endpoint."""
    a = _ev_appraisal(users, AppraisalStatus.LOCKED)
    resp = client.post(
        f"/api/v1/appraisals/{a.id}/resolve-contestation",
        json={"resolution_note": "tarde demais"},
        headers=_auth_header(users["admin"]),
    )
    assert resp.status_code == 409
    db.session.refresh(a)
    assert a.status == AppraisalStatus.LOCKED
    assert a.has_contestation is True
    assert a.locked_at is not None


# ── CN monthly ────────────────────────────────────────────────────────


def test_cn_single_finalize_blocked_then_passes_after_resolve(
        client, db_session, users):
    a = _cn_appraisal(users, AppraisalStatus.VALIDATING, contested=False)
    admin = _auth_header(users["admin"])

    # CN contests through the real endpoint (routes to REVOPS_REVIEW).
    resp = client.post(
        f"/api/v1/commissions/cn/appraisal/{a.id}/contest",
        json={"note": "score errado"}, headers=_auth_header(users["cn"]),
    )
    assert resp.status_code == 200

    # The single-row finalize must respect the contestation like the bulks do.
    resp = client.post(
        f"/api/v1/commissions/cn/appraisal/{a.id}/finalize", headers=admin,
    )
    assert resp.status_code == 422
    db.session.refresh(a)
    assert a.status != AppraisalStatus.LOCKED

    resp = client.post(
        f"/api/v1/commissions/cn/appraisal/{a.id}/resolve-contestation",
        json={"resolution_note": "corrigido"}, headers=admin,
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/api/v1/commissions/cn/appraisal/{a.id}/finalize", headers=admin,
    )
    assert resp.status_code == 200
    db.session.refresh(a)
    assert a.status == AppraisalStatus.LOCKED


def test_cn_transition_to_locked_blocked_with_contestation(
        client, db_session, users):
    a = _cn_appraisal(users, AppraisalStatus.REVOPS_REVIEW)
    resp = client.post(
        f"/api/v1/commissions/cn/appraisal/{a.id}/transition",
        json={"to": "LOCKED"}, headers=_auth_header(users["admin"]),
    )
    assert resp.status_code == 422
    db.session.refresh(a)
    assert a.status == AppraisalStatus.REVOPS_REVIEW


def test_cn_resolve_rejected_after_lock(client, db_session, users):
    a = _cn_appraisal(users, AppraisalStatus.LOCKED)
    resp = client.post(
        f"/api/v1/commissions/cn/appraisal/{a.id}/resolve-contestation",
        json={"resolution_note": "tarde"}, headers=_auth_header(users["admin"]),
    )
    assert resp.status_code == 409
    db.session.refresh(a)
    assert a.status == AppraisalStatus.LOCKED
    assert a.has_contestation is True


# ── Leadership quarterly (state machine level — no contest route yet) ─


def test_leadership_lock_blocked_with_contestation(db_session, users):
    a = LiderVendasQuarterAppraisal(
        lider_vendas_id=users["lider"].id, quarter=2, year=2026,
        meta_mrr=Decimal("1000"), meta_sql=10,
        realizado_mrr=Decimal("900"), realizado_sql=9,
        pct_mrr=Decimal("0.9"), pct_sql=Decimal("0.9"),
        multiplicador=Decimal("1.0"), bonus_amount=Decimal("300.00"),
        status=AppraisalStatus.REVOPS_REVIEW,
        has_contestation=True, contestation_note="meta errada",
    )
    db.session.add(a)
    db.session.commit()

    with pytest.raises(InvalidTransitionError):
        transition_lider_vendas_appraisal(a, AppraisalStatus.LOCKED)
    assert a.status == AppraisalStatus.REVOPS_REVIEW
