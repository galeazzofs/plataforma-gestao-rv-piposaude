"""Tests for PUT /api/v1/policies/{id} manual override endpoint.

Note: the PUT endpoint calls db.session.commit(), so we clean up
explicitly at the end of each test rather than relying on session rollback.
"""
import uuid
from datetime import date

import pytest

from app.extensions import db
from app.models import (
    User, UserRole, Policy, Client, Segment, BenefitType, CommissionStatus, AuditLog,
)
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fresh_actors():
    """Create admin + ev with unique emails per test. Cleans up committed
    data at the end via explicit delete."""
    suffix = uuid.uuid4().hex[:8]
    admin = User(
        email=f"put-admin-{suffix}@x", name="Admin",
        role=UserRole.ADMIN, active=True,
    )
    ev = User(
        email=f"put-ev-{suffix}@x", name="EV",
        role=UserRole.EV, active=True,
    )
    db.session.add_all([admin, ev])
    db.session.flush()
    client = Client.find_or_create(f"PutClient-{suffix}")
    db.session.flush()
    db.session.commit()

    yield admin, ev, client

    # Teardown: remove committed rows
    Policy.query.filter(Policy.client_id == client.id).delete()
    AuditLog.query.filter_by(table_name="policies").delete()
    db.session.delete(client)
    db.session.delete(admin)
    db.session.delete(ev)
    db.session.commit()


def _make_policy(ev_id, client_id, ticket_id="PUT-T"):
    ticket_uuid = uuid.uuid4().hex[:6]
    p = Policy(
        hubspot_apolice_id=f"A-{ticket_id}-{ticket_uuid}",
        hubspot_ticket_id=f"{ticket_id}-{ticket_uuid}",
        ev_id=ev_id,
        client_id=client_id,
        segment=Segment.M,
        benefit_type=BenefitType.SAUDE,
        partner_operator="SulAmerica",
        closed_date=date(2025, 12, 1),
        initial_installments_paid=0,
    )
    db.session.add(p)
    db.session.commit()
    return p


def test_put_policy_updates_initial_installments_paid(client, fresh_actors):
    admin, ev, client_obj = fresh_actors
    p = _make_policy(ev.id, client_obj.id, "IIP")

    resp = client.put(
        f"/api/v1/policies/{p.id}",
        json={"initial_installments_paid": 6},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200

    db.session.expire(p)
    assert p.initial_installments_paid == 6
    assert p.is_locked is True


def test_put_policy_creates_audit_log_entry(client, fresh_actors):
    admin, ev, client_obj = fresh_actors
    p = _make_policy(ev.id, client_obj.id, "AUDIT")

    client.put(
        f"/api/v1/policies/{p.id}",
        json={"initial_installments_paid": 6},
        headers=_auth_header(admin),
    )

    log = AuditLog.query.filter_by(
        table_name="policies", record_id=p.id
    ).first()
    assert log is not None
    assert log.action == "UPDATE"
    assert "initial_installments_paid" in (log.new_values or {})


def test_put_policy_returns_404_for_unknown_id(client, fresh_actors):
    admin, _, _ = fresh_actors
    resp = client.put(
        "/api/v1/policies/00000000-0000-0000-0000-000000000000",
        json={"initial_installments_paid": 6},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 404


def test_put_policy_requires_admin(client, fresh_actors):
    _, ev, client_obj = fresh_actors
    p = _make_policy(ev.id, client_obj.id, "NOADM")

    resp = client.put(
        f"/api/v1/policies/{p.id}",
        json={"initial_installments_paid": 6},
        headers=_auth_header(ev),
    )
    assert resp.status_code in (401, 403)


def test_put_policy_updates_first_payment_real_and_segment(client, fresh_actors):
    admin, ev, client_obj = fresh_actors
    p = _make_policy(ev.id, client_obj.id, "MULTI")

    resp = client.put(
        f"/api/v1/policies/{p.id}",
        json={
            "first_payment_real": "2026-02-01",
            "segment": "G",
        },
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200

    db.session.expire(p)
    assert p.first_payment_real == date(2026, 2, 1)
    assert p.segment == Segment.G
    assert p.is_locked is True


def test_get_policies_applies_active_ev_filter(client, fresh_actors):
    """GET /policies as ADMIN returns ALL policies (active + inactive EVs).
    EV/CN/GERENTE roles get only active EV policies (covered elsewhere)."""
    admin, active_ev, client_obj = fresh_actors
    suffix = uuid.uuid4().hex[:8]
    inactive_ev = User(
        email=f"put-inact-{suffix}@x", name="Inactive",
        role=UserRole.EV, active=False,
    )
    db.session.add(inactive_ev)
    db.session.commit()

    active_ticket = f"ACTIVE-{suffix}"
    inactive_ticket = f"INACTIVE-{suffix}"
    p_active = Policy(
        hubspot_apolice_id=f"A-{active_ticket}",
        hubspot_ticket_id=active_ticket,
        ev_id=active_ev.id, client_id=client_obj.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 12, 1),
    )
    p_inactive = Policy(
        hubspot_apolice_id=f"A-{inactive_ticket}",
        hubspot_ticket_id=inactive_ticket,
        ev_id=inactive_ev.id, client_id=client_obj.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 12, 1),
    )
    db.session.add_all([p_active, p_inactive])
    db.session.commit()

    try:
        resp = client.get(
            "/api/v1/policies",
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        ticket_ids = {p["hubspot_ticket_id"] for p in data}
        assert active_ticket in ticket_ids
        # ADMIN sees the complete picture — inactive EVs are NOT hidden
        assert inactive_ticket in ticket_ids
    finally:
        Policy.query.filter(Policy.id.in_([p_active.id, p_inactive.id])).delete()
        db.session.delete(inactive_ev)
        db.session.commit()


def test_get_policies_filters_by_status(client, fresh_actors):
    admin, ev, client_obj = fresh_actors
    suffix = uuid.uuid4().hex[:8]
    projected_ticket = f"STATUS-PROJECTED-{suffix}"
    settled_ticket = f"STATUS-SETTLED-{suffix}"
    p_projected = Policy(
        hubspot_apolice_id=f"A-{projected_ticket}",
        hubspot_ticket_id=projected_ticket,
        ev_id=ev.id, client_id=client_obj.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        commission_status=CommissionStatus.PROJECTED,
        closed_date=date(2025, 12, 1),
    )
    p_settled = Policy(
        hubspot_apolice_id=f"A-{settled_ticket}",
        hubspot_ticket_id=settled_ticket,
        ev_id=ev.id, client_id=client_obj.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        commission_status=CommissionStatus.SETTLED,
        closed_date=date(2025, 12, 1),
    )
    db.session.add_all([p_projected, p_settled])
    db.session.commit()

    resp = client.get(
        f"/api/v1/policies?status=SETTLED&search={suffix}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    ticket_ids = {p["hubspot_ticket_id"] for p in resp.get_json()["data"]}
    assert settled_ticket in ticket_ids
    assert projected_ticket not in ticket_ids


def test_get_policies_searches_client_ev_and_policy_fields(client, fresh_actors):
    admin, ev, client_obj = fresh_actors
    suffix = uuid.uuid4().hex[:8]
    ev.name = f"Search EV {suffix}"
    client_obj.name = f"Search Client {suffix}"
    p = Policy(
        hubspot_apolice_id=f"APOLICE-{suffix}",
        hubspot_ticket_id=f"TICKET-{suffix}",
        numero_apolice=f"NUM-{suffix}",
        partner_operator=f"Operadora {suffix}",
        ev_id=ev.id, client_id=client_obj.id,
        segment=Segment.M, benefit_type=BenefitType.SAUDE,
        closed_date=date(2025, 12, 1),
    )
    db.session.add(p)
    db.session.commit()

    for term in [client_obj.name, ev.name, p.hubspot_ticket_id, p.numero_apolice]:
        resp = client.get(
            "/api/v1/policies",
            query_string={"search": term},
            headers=_auth_header(admin),
        )
        assert resp.status_code == 200
        ticket_ids = {row["hubspot_ticket_id"] for row in resp.get_json()["data"]}
        assert p.hubspot_ticket_id in ticket_ids
