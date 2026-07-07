"""API da conferência por EV: marcar, reabrir, authz, estados, gate, payload."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    Appraisal, AppraisalStatus, BenefitType, Client, Commission,
    EvSignoff, Policy, Segment, SignoffStatus, User, UserRole,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def signoff_setup():
    """Admin + 2 EVs ativos; EV1 tem apólice + Commission na apuração
    09/2026 em CALCULATING; EV2 é ativo sem movimento."""
    suffix = uuid.uuid4().hex[:8]
    admin = User(email=f"soa-admin-{suffix}@x", name="Admin",
                 role=UserRole.ADMIN, active=True)
    ev1 = User(email=f"soa-ev1-{suffix}@x", name=f"Alice {suffix}",
               role=UserRole.EV, active=True)
    ev2 = User(email=f"soa-ev2-{suffix}@x", name=f"Bruno {suffix}",
               role=UserRole.EV, active=True)
    db.session.add_all([admin, ev1, ev2])
    db.session.flush()

    client_obj = Client.find_or_create(f"SoaClient-{suffix}")
    db.session.flush()
    policy = Policy(
        hubspot_ticket_id=f"SOA-{suffix}",
        numero_apolice=f"AP-SOA-{suffix}",
        ev_id=ev1.id, client_id=client_obj.id,
        segment=Segment.P, benefit_type=BenefitType.SAUDE,
        partner_operator="Amil", closed_date=date(2026, 7, 1),
    )
    db.session.add(policy)
    db.session.flush()

    appraisal = Appraisal(month=9, year=2026,
                          status=AppraisalStatus.CALCULATING,
                          created_by=admin.id)
    db.session.add(appraisal)
    db.session.flush()

    comm = Commission(
        policy_id=policy.id, ev_id=ev1.id, month=9, year=2026,
        segment="P", achievement_pct=Decimal("0.75"),
        commission_pct=Decimal("0.08"),
        monthly_actual=Decimal("80.00"), total_actual=Decimal("80.00"),
        is_final=False,
    )
    db.session.add(comm)
    db.session.commit()
    return admin, ev1, ev2, policy, appraisal, comm


def test_signoff_and_reopen_roundtrip(client, signoff_setup):
    from app.models import AuditLog

    admin, ev1, ev2, _, appraisal, _ = signoff_setup

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["ev_id"] == str(ev1.id)
    assert data["signoff"]["status"] == "DONE"
    assert data["signoff"]["signed_off_by_name"] == admin.name
    assert data["signoff"]["values_changed"] is False
    assert data["signoff_totals"] == {"total": 2, "done": 1,
                                      "all_done": False}
    assert AuditLog.query.filter_by(table_name="ev_signoffs").count() == 1

    # idempotente
    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["signoff_totals"]["done"] == 1

    # reabrir
    resp = client.delete(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["signoff"]["status"] == "PENDING"
    assert data["signoff_totals"]["done"] == 0


def test_signoff_requires_admin(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup
    url = f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}"

    resp = client.post(url, headers=_auth_header(ev1))
    assert resp.status_code == 403
    resp = client.delete(url, headers=_auth_header(ev1))
    assert resp.status_code == 403


def test_signoff_only_in_calculating(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup
    appraisal.status = AppraisalStatus.VALIDATING
    db.session.commit()

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "INVALID_STATE"


def test_signoff_out_of_scope_and_not_found(client, signoff_setup):
    admin, ev1, _, _, appraisal, _ = signoff_setup

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/{admin.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400          # ADMIN não é EV do escopo

    resp = client.post(
        f"/api/v1/appraisals/{uuid.uuid4()}/signoffs/{ev1.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 404

    resp = client.post(
        f"/api/v1/appraisals/{appraisal.id}/signoffs/nao-e-uuid",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400


def test_release_gate_via_api(client, signoff_setup):
    admin, ev1, ev2, _, appraisal, _ = signoff_setup
    url = f"/api/v1/appraisals/{appraisal.id}/transition"

    resp = client.post(url, json={"to": "VALIDATING"},
                       headers=_auth_header(admin))
    assert resp.status_code == 422
    assert "sem conferência" in resp.get_json()["error"]["message"]

    for ev in (ev1, ev2):
        resp = client.post(
            f"/api/v1/appraisals/{appraisal.id}/signoffs/{ev.id}",
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200

    resp = client.post(url, json={"to": "VALIDATING"},
                       headers=_auth_header(admin))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "VALIDATING"
