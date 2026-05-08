"""Tests for the contestation flow on quarterly Appraisal (issue #36)."""
import uuid

import pytest

from app.extensions import db
from app.models import Appraisal, AppraisalStatus, AuditLog, User, UserRole
from app.auth.jwt_manager import create_access_token


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def appraisal_setup():
    """Admin + EV + an Appraisal sitting in VALIDATING."""
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"ct-admin-{suffix}@x", name="CT Admin",
                 role=UserRole.ADMIN, active=True)
    ev = User(email=f"ct-ev-{suffix}@x", name="CT EV",
              role=UserRole.EV, active=True)
    db.session.add_all([admin, ev])
    db.session.flush()

    appraisal = Appraisal(
        quarter=1, year=2031,
        status=AppraisalStatus.VALIDATING,
        created_by=admin.id,
    )
    db.session.add(appraisal)
    db.session.commit()

    yield {"admin": admin, "ev": ev, "appraisal": appraisal}

    AuditLog.query.filter(
        AuditLog.user_id.in_([admin.id, ev.id])
    ).delete(synchronize_session=False)
    db.session.delete(appraisal)
    db.session.delete(ev)
    db.session.delete(admin)
    db.session.commit()


def test_contest_routes_to_revops_review(client, appraisal_setup):
    s = appraisal_setup
    resp = client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/contest",
        json={"note": "Valor MRR está errado, não bate com a NF de junho."},
        headers=_auth(s["ev"]),
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["status"] == "REVOPS_REVIEW"
    assert body["has_contestation"] is True
    assert "junho" in body["contestation_note"]


def test_contest_requires_note(client, appraisal_setup):
    s = appraisal_setup
    resp = client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/contest",
        json={"note": "  "},
        headers=_auth(s["ev"]),
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_contest_blocked_outside_validating(client, appraisal_setup):
    s = appraisal_setup
    s["appraisal"].status = AppraisalStatus.LIDER_REVIEW
    db.session.commit()

    resp = client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/contest",
        json={"note": "Tarde demais"},
        headers=_auth(s["ev"]),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "INVALID_STATE"


def test_resolve_contestation_routes_back_to_validating(client, appraisal_setup):
    s = appraisal_setup
    client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/contest",
        json={"note": "Conferir o cálculo do trimestre."},
        headers=_auth(s["ev"]),
    )

    resp = client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/resolve-contestation",
        json={"resolution_note": "Recalculei e o valor está correto. Validar novamente."},
        headers=_auth(s["admin"]),
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["status"] == "VALIDATING"
    assert body["has_contestation"] is False
    assert "Recalculei" in body["resolution_note"]


def test_resolve_requires_note(client, appraisal_setup):
    s = appraisal_setup
    client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/contest",
        json={"note": "Vamos discutir"},
        headers=_auth(s["ev"]),
    )
    resp = client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/resolve-contestation",
        json={"resolution_note": ""},
        headers=_auth(s["admin"]),
    )
    assert resp.status_code == 400


def test_resolve_only_when_contestation_open(client, appraisal_setup):
    s = appraisal_setup
    resp = client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/resolve-contestation",
        json={"resolution_note": "Não há contestação"},
        headers=_auth(s["admin"]),
    )
    assert resp.status_code == 409


def test_resolve_requires_admin(client, appraisal_setup):
    s = appraisal_setup
    client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/contest",
        json={"note": "Conferir"},
        headers=_auth(s["ev"]),
    )
    resp = client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/resolve-contestation",
        json={"resolution_note": "Tentando como EV"},
        headers=_auth(s["ev"]),
    )
    assert resp.status_code == 403


def test_state_machine_blocks_lider_review_with_open_contestation(client, appraisal_setup):
    """If somehow has_contestation is set while in VALIDATING, the
    transition to LIDER_REVIEW must be rejected by the state machine."""
    s = appraisal_setup
    # Force a contestation flag without going through the contest endpoint
    s["appraisal"].has_contestation = True
    db.session.commit()

    resp = client.post(
        f"/api/v1/appraisals/{s['appraisal'].id}/transition",
        json={"to": "LIDER_REVIEW"},
        headers=_auth(s["admin"]),
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "INVALID_TRANSITION"
