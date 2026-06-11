"""Ownership tests for the per-EV commission reads.

GET /commissions/summary and /commissions/projection take an ev_id query
param. The user's own id must be enforced — not just defaulted: an EV/CN
passing someone else's id is an IDOR; a líder may only target the own team;
ADMIN/FINANCE stay unrestricted.
"""
import uuid

import pytest

from app.extensions import db
from app.models import User, UserRole, Team
from app.auth.jwt_manager import create_access_token

ENDPOINTS = ("/api/v1/commissions/summary", "/api/v1/commissions/projection")


def _auth_header(user):
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def scope_setup():
    """ev_a belongs to team A (led by lider_a); ev_b has no team — the
    foreign target for everyone and the IS-NULL trap for the teamless líder."""
    suffix = uuid.uuid4().hex[:8]

    team_a = Team(name=f"Time A {suffix}")
    db.session.add(team_a)
    db.session.flush()

    users = {
        "admin": User(email=f"adm-{suffix}@x", name="Admin",
                      role=UserRole.ADMIN, active=True),
        "finance": User(email=f"fin-{suffix}@x", name="Finance",
                        role=UserRole.FINANCE, active=True),
        "lider_a": User(email=f"lid-a-{suffix}@x", name="Lider A",
                        role=UserRole.LIDER_VENDAS, active=True,
                        team_id=team_a.id),
        "lider_sem_time": User(email=f"lid-0-{suffix}@x", name="Lider 0",
                               role=UserRole.LIDER_VENDAS, active=True,
                               team_id=None),
        "ev_a": User(email=f"ev-a-{suffix}@x", name="EV Alice",
                     role=UserRole.EV, active=True, team_id=team_a.id),
        "ev_b": User(email=f"ev-b-{suffix}@x", name="EV Bruno",
                     role=UserRole.EV, active=True, team_id=None),
        "cn": User(email=f"cn-{suffix}@x", name="CN Carla",
                   role=UserRole.CN, active=True),
    }
    db.session.add_all(users.values())
    db.session.commit()
    return users


def _get(client, endpoint, as_user, ev_id=None):
    qs = f"?ev_id={ev_id}" if ev_id is not None else ""
    return client.get(endpoint + qs, headers=_auth_header(as_user))


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_ev_with_foreign_ev_id_is_forbidden(client, db_session, scope_setup, endpoint):
    resp = _get(client, endpoint, scope_setup["ev_a"],
                ev_id=scope_setup["ev_b"].id)
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_cn_with_foreign_ev_id_is_forbidden(client, db_session, scope_setup, endpoint):
    resp = _get(client, endpoint, scope_setup["cn"],
                ev_id=scope_setup["ev_a"].id)
    assert resp.status_code == 403


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_ev_reads_own_data(client, db_session, scope_setup, endpoint):
    # Default (no param) and the own id spelled out both work.
    assert _get(client, endpoint, scope_setup["ev_a"]).status_code == 200
    resp = _get(client, endpoint, scope_setup["ev_a"],
                ev_id=scope_setup["ev_a"].id)
    assert resp.status_code == 200


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_lider_scoped_to_own_team(client, db_session, scope_setup, endpoint):
    lider = scope_setup["lider_a"]
    assert _get(client, endpoint, lider,
                ev_id=scope_setup["ev_a"].id).status_code == 200
    assert _get(client, endpoint, lider,
                ev_id=scope_setup["ev_b"].id).status_code == 403
    # No target → unchanged contract: explicit 400.
    assert _get(client, endpoint, lider).status_code == 400


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_lider_without_team_has_no_scope(client, db_session, scope_setup, endpoint):
    resp = _get(client, endpoint, scope_setup["lider_sem_time"],
                ev_id=scope_setup["ev_b"].id)
    assert resp.status_code == 403


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_lider_with_garbage_ev_id_gets_403_not_500(client, db_session, scope_setup, endpoint):
    resp = _get(client, endpoint, scope_setup["lider_a"], ev_id="not-a-uuid")
    assert resp.status_code == 403


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_admin_and_finance_read_any_ev(client, db_session, scope_setup, endpoint):
    for who in ("admin", "finance"):
        resp = _get(client, endpoint, scope_setup[who],
                    ev_id=scope_setup["ev_b"].id)
        assert resp.status_code == 200
    # Unchanged contract: target required for unrestricted roles.
    assert _get(client, endpoint, scope_setup["admin"]).status_code == 400
