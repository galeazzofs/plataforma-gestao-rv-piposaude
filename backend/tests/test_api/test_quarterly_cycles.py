"""Tests for /api/v1/quarterly-cycles endpoints (issue #32)."""
import uuid

import pytest

from app.extensions import db
from app.models import User, UserRole, QuarterlyCycle, QuarterlyCycleStatus
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin():
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"qc-admin-{suffix}@x",
        name="QC Admin",
        role=UserRole.ADMIN,
        active=True,
    )
    db.session.add(u)
    db.session.flush()
    return u


@pytest.fixture
def ev():
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"qc-ev-{suffix}@x",
        name="QC EV",
        role=UserRole.EV,
        active=True,
    )
    db.session.add(u)
    db.session.flush()
    return u


def test_create_cycle_returns_open(client, admin):
    resp = client.post(
        "/api/v1/quarterly-cycles",
        json={"quarter": 1, "year": 2030},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["quarter"] == 1
    assert data["year"] == 2030
    assert data["status"] == "OPEN"
    assert data["created_by"] == str(admin.id)
    assert data["locked_at"] is None


def test_create_cycle_blocks_duplicate(client, admin):
    db.session.add(QuarterlyCycle(
        quarter=2, year=2030,
        status=QuarterlyCycleStatus.OPEN,
        created_by=admin.id,
    ))
    db.session.flush()

    resp = client.post(
        "/api/v1/quarterly-cycles",
        json={"quarter": 2, "year": 2030},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CONFLICT"


def test_create_cycle_validates_quarter(client, admin):
    resp = client.post(
        "/api/v1/quarterly-cycles",
        json={"quarter": 5, "year": 2030},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_cycle_requires_admin(client, ev):
    resp = client.post(
        "/api/v1/quarterly-cycles",
        json={"quarter": 3, "year": 2030},
        headers=_auth_header(ev),
    )
    assert resp.status_code == 403


def test_list_cycles_returns_newest_first(client, admin):
    db.session.add_all([
        QuarterlyCycle(
            quarter=1, year=2031,
            status=QuarterlyCycleStatus.OPEN, created_by=admin.id,
        ),
        QuarterlyCycle(
            quarter=4, year=2030,
            status=QuarterlyCycleStatus.LOCKED, created_by=admin.id,
        ),
    ])
    db.session.flush()

    resp = client.get(
        "/api/v1/quarterly-cycles", headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    items = resp.get_json()["data"]
    pairs = [(c["quarter"], c["year"]) for c in items]
    # Newest (year desc, quarter desc) first
    idx_31q1 = pairs.index((1, 2031))
    idx_30q4 = pairs.index((4, 2030))
    assert idx_31q1 < idx_30q4


def test_get_cycle_returns_team_components(client, admin):
    cycle = QuarterlyCycle(
        quarter=2, year=2031,
        status=QuarterlyCycleStatus.OPEN,
        created_by=admin.id,
    )
    db.session.add(cycle)
    db.session.flush()

    resp = client.get(
        f"/api/v1/quarterly-cycles/{cycle.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["quarter"] == 2
    assert body["year"] == 2031
    assert "teams" in body
    # Each team block has the 5 component keys.
    for team in body["teams"]:
        assert set(team["components"].keys()) == {
            "ev_quarter", "cn_monthly", "cn_quarterly_bonus",
            "ev_quarterly_bonus", "leadership",
        }


def test_get_cycle_404(client, admin):
    fake_id = str(uuid.uuid4())
    resp = client.get(
        f"/api/v1/quarterly-cycles/{fake_id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 404
