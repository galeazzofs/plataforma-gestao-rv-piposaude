"""Tests for /api/v1/monthly-cycles endpoints."""
import uuid

import pytest

from app.extensions import db
from app.models import User, UserRole, MonthlyCycle, MonthlyCycleStatus
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin():
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"mc-admin-{suffix}@x",
        name="MC Admin",
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
        email=f"mc-ev-{suffix}@x",
        name="MC EV",
        role=UserRole.EV,
        active=True,
    )
    db.session.add(u)
    db.session.flush()
    return u


def test_create_cycle_returns_open(client, admin):
    resp = client.post(
        "/api/v1/monthly-cycles",
        json={"month": 1, "year": 2030},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["month"] == 1
    assert data["year"] == 2030
    assert data["quarter"] == 1
    assert data["is_quarter_end"] is False
    assert data["status"] == "OPEN"
    assert data["created_by"] == str(admin.id)
    assert data["locked_at"] is None


def test_create_quarter_end_cycle_flags_quarter_end(client, admin):
    resp = client.post(
        "/api/v1/monthly-cycles",
        json={"month": 6, "year": 2030},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["quarter"] == 2
    assert data["is_quarter_end"] is True


def test_create_cycle_blocks_duplicate(client, admin):
    db.session.add(MonthlyCycle(
        month=2, year=2030,
        status=MonthlyCycleStatus.OPEN,
        created_by=admin.id,
    ))
    db.session.flush()

    resp = client.post(
        "/api/v1/monthly-cycles",
        json={"month": 2, "year": 2030},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CONFLICT"


def test_create_cycle_validates_month(client, admin):
    resp = client.post(
        "/api/v1/monthly-cycles",
        json={"month": 13, "year": 2030},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_cycle_requires_admin(client, ev):
    resp = client.post(
        "/api/v1/monthly-cycles",
        json={"month": 3, "year": 2030},
        headers=_auth_header(ev),
    )
    assert resp.status_code == 403


def test_list_cycles_returns_newest_first(client, admin):
    db.session.add_all([
        MonthlyCycle(
            month=1, year=2031,
            status=MonthlyCycleStatus.OPEN, created_by=admin.id,
        ),
        MonthlyCycle(
            month=12, year=2030,
            status=MonthlyCycleStatus.LOCKED, created_by=admin.id,
        ),
    ])
    db.session.flush()

    resp = client.get(
        "/api/v1/monthly-cycles", headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    items = resp.get_json()["data"]
    pairs = [(c["month"], c["year"]) for c in items]
    # Newest (year desc, month desc) first
    idx_31m1 = pairs.index((1, 2031))
    idx_30m12 = pairs.index((12, 2030))
    assert idx_31m1 < idx_30m12


def test_get_cycle_returns_base_sequence_components(client, admin):
    """A non-quarter-end month carries only the two apuração components."""
    cycle = MonthlyCycle(
        month=4, year=2031,
        status=MonthlyCycleStatus.OPEN,
        created_by=admin.id,
    )
    db.session.add(cycle)
    db.session.flush()

    resp = client.get(
        f"/api/v1/monthly-cycles/{cycle.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["month"] == 4
    assert body["year"] == 2031
    assert body["is_quarter_end"] is False
    assert body["sequence"] == ["ev_apuracao", "cn_apuracao"]
    assert "teams" not in body
    assert set(body["components"].keys()) == {"ev_apuracao", "cn_apuracao"}
    assert body["components"]["ev_apuracao"]["status"] == "PENDING"


def test_get_quarter_end_cycle_returns_bonus_components(client, admin):
    """Quarter-end months append the three quarterly bonus components."""
    cycle = MonthlyCycle(
        month=6, year=2031,
        status=MonthlyCycleStatus.OPEN,
        created_by=admin.id,
    )
    db.session.add(cycle)
    db.session.flush()

    resp = client.get(
        f"/api/v1/monthly-cycles/{cycle.id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["is_quarter_end"] is True
    assert body["sequence"] == [
        "ev_apuracao", "cn_apuracao", "cn_bonus", "ev_bonus",
        "leadership_bonus",
    ]
    assert "teams" not in body
    assert set(body["components"].keys()) == {
        "ev_apuracao", "cn_apuracao", "cn_bonus", "ev_bonus",
        "leadership_bonus",
    }


def test_get_cycle_404(client, admin):
    fake_id = str(uuid.uuid4())
    resp = client.get(
        f"/api/v1/monthly-cycles/{fake_id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 404


def test_delete_cycle_open(client, admin):
    cycle = MonthlyCycle(
        month=7, year=2031,
        status=MonthlyCycleStatus.OPEN, created_by=admin.id,
    )
    db.session.add(cycle)
    db.session.flush()
    cycle_id = str(cycle.id)

    resp = client.delete(
        f"/api/v1/monthly-cycles/{cycle_id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["deleted"] is True
    assert db.session.get(MonthlyCycle, cycle_id) is None


def test_delete_cycle_blocks_when_locked(client, admin):
    cycle = MonthlyCycle(
        month=8, year=2031,
        status=MonthlyCycleStatus.LOCKED, created_by=admin.id,
    )
    db.session.add(cycle)
    db.session.flush()
    cycle_id = str(cycle.id)

    resp = client.delete(
        f"/api/v1/monthly-cycles/{cycle_id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CONFLICT"
    assert db.session.get(MonthlyCycle, cycle_id) is not None


def test_delete_cycle_404(client, admin):
    fake_id = str(uuid.uuid4())
    resp = client.delete(
        f"/api/v1/monthly-cycles/{fake_id}",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 404


def test_delete_cycle_requires_admin(client, ev, admin):
    cycle = MonthlyCycle(
        month=9, year=2032,
        status=MonthlyCycleStatus.OPEN, created_by=admin.id,
    )
    db.session.add(cycle)
    db.session.flush()

    resp = client.delete(
        f"/api/v1/monthly-cycles/{cycle.id}",
        headers=_auth_header(ev),
    )
    assert resp.status_code == 403
