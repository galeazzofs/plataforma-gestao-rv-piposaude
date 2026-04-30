"""Test that updating hubspot_owner_map clears the sync cursor so previously
skipped tickets get re-fetched on the next sync."""
import uuid

import pytest

from app.extensions import db
from app.models import User, UserRole, PlatformSetting, AuditLog
from app.auth.jwt_manager import create_access_token


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin():
    suffix = uuid.uuid4().hex[:8]
    u = User(
        email=f"settings-admin-{suffix}@x", name="Admin",
        role=UserRole.ADMIN, active=True,
    )
    db.session.add(u)
    db.session.commit()
    yield u
    PlatformSetting.query.filter(
        PlatformSetting.key.in_([
            "hubspot_owner_map",
            "hubspot_sync_last_success_at",
            "default_quarterly_target",
        ])
    ).delete(synchronize_session=False)
    PlatformSetting.query.filter_by(updated_by=u.id).delete(synchronize_session=False)
    AuditLog.query.filter_by(user_id=u.id).delete()
    db.session.delete(u)
    db.session.commit()


def test_putting_hubspot_owner_map_clears_sync_cursor(client, admin):
    PlatformSetting.set("hubspot_sync_last_success_at", "2026-04-01T00:00:00+00:00", user_id=None)
    db.session.commit()

    resp = client.put(
        "/api/v1/admin/settings/hubspot_owner_map",
        headers=_auth_header(admin),
        json={"value": {"61760774": "ev@piposaude.com"}},
    )
    assert resp.status_code == 200

    assert PlatformSetting.get("hubspot_sync_last_success_at") is None


def test_bulk_update_with_owner_map_clears_sync_cursor(client, admin):
    PlatformSetting.set("hubspot_sync_last_success_at", "2026-04-01T00:00:00+00:00", user_id=None)
    db.session.commit()

    resp = client.put(
        "/api/v1/admin/settings",
        headers=_auth_header(admin),
        json={"settings": {"hubspot_owner_map": {"61760774": "ev@piposaude.com"}}},
    )
    assert resp.status_code == 200

    assert PlatformSetting.get("hubspot_sync_last_success_at") is None


def test_putting_unrelated_setting_preserves_sync_cursor(client, admin):
    PlatformSetting.set("hubspot_sync_last_success_at", "2026-04-01T00:00:00+00:00", user_id=None)
    db.session.commit()

    resp = client.put(
        "/api/v1/admin/settings/default_quarterly_target",
        headers=_auth_header(admin),
        json={"value": "100000"},
    )
    assert resp.status_code == 200

    assert PlatformSetting.get("hubspot_sync_last_success_at") == "2026-04-01T00:00:00+00:00"
