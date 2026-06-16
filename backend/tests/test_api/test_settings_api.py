"""Admin platform-settings endpoints.

The settings API is intentionally free-form: any key may be written, but only
by an ADMIN (every route is require_role(ADMIN)). There is deliberately no
writable-key allowlist — the RevOps settings page bulk-saves an open map of
keys (deadlines, notification toggles, HubSpot owner map, CN rampagem bonus,
…) and the sync pipeline writes ad-hoc status keys. These tests pin that
contract so a future allowlist isn't reintroduced without updating them.
"""
import uuid

from app.auth.jwt_manager import create_access_token
from app.models import User, UserRole


def _auth(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


def _make_user(db_session, role):
    u = User(
        email=f"{role.value.lower()}-{uuid.uuid4().hex[:8]}@piposaude.com",
        name=role.value,
        role=role,
        active=True,
    )
    db_session.add(u)
    db_session.flush()
    return u


def test_admin_can_write_arbitrary_key_single(client, db_session):
    """An admin can write a key that was never in any allowlist; it round-trips."""
    admin = _make_user(db_session, UserRole.ADMIN)
    key = f"some_freeform_key_{uuid.uuid4().hex[:6]}"

    put = client.put(f"/api/v1/admin/settings/{key}",
                     headers=_auth(admin), json={"value": "42"})
    assert put.status_code == 200
    assert put.get_json()["data"] == {"key": key, "value": "42"}

    listing = client.get("/api/v1/admin/settings", headers=_auth(admin)).get_json()
    assert listing["data"][key] == "42"


def test_admin_bulk_write_multiple_keys(client, db_session):
    """Bulk PUT persists an open map of keys (mirrors the settings page save)."""
    admin = _make_user(db_session, UserRole.ADMIN)
    payload = {
        "validation_deadline_days": 5,
        "notify_finance_approval": True,
        f"adhoc_{uuid.uuid4().hex[:6]}": "x",
    }
    put = client.put("/api/v1/admin/settings",
                     headers=_auth(admin), json={"settings": payload})
    assert put.status_code == 200

    listing = client.get("/api/v1/admin/settings", headers=_auth(admin)).get_json()
    for k, v in payload.items():
        assert listing["data"][k] == v


def test_non_admin_cannot_read_or_write_settings(client, db_session):
    """Every settings route is ADMIN-only — a CN is rejected."""
    cn = _make_user(db_session, UserRole.CN)

    assert client.get("/api/v1/admin/settings",
                      headers=_auth(cn)).status_code == 403
    assert client.put("/api/v1/admin/settings/whatever",
                      headers=_auth(cn), json={"value": "1"}).status_code == 403
    assert client.put("/api/v1/admin/settings",
                      headers=_auth(cn), json={"settings": {"a": 1}}).status_code == 403
