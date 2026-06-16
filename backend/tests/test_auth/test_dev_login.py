"""Dev-login gating.

The dev-only login picker must work under a normal `flask run` — which forces
app.config["DEBUG"] = False even in dev — yet stay shut in stag/prod. See
_dev_login_enabled() in app/api/v1/auth.py.
"""
import pytest

from app.models import User, UserRole


@pytest.fixture
def _dev_picker_user(db_session):
    user = User(
        email="dev.picker@piposaude.com",
        name="Dev Picker",
        role=UserRole.EV,
        active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_dev_users_listed_even_when_debug_off(client, app, monkeypatch, _dev_picker_user):
    """Regression: gating on DEBUG 403'd the picker under a plain `flask run`,
    which sets DEBUG=False in dev. The dev-only DEV_LOGIN_ALLOWED flag keeps the
    endpoint working regardless of DEBUG."""
    monkeypatch.setenv("DEV_LOGIN_ENABLED", "true")
    monkeypatch.setitem(app.config, "DEV_LOGIN_ALLOWED", True)
    monkeypatch.setitem(app.config, "DEBUG", False)  # what `flask run` does in dev

    response = client.get("/api/v1/auth/dev-users")

    assert response.status_code == 200
    emails = [u["email"] for u in response.json["data"]]
    assert "dev.picker@piposaude.com" in emails


def test_dev_users_forbidden_without_env_opt_in(client, app, monkeypatch):
    """Defense-in-depth: a dev-flagged config alone is not enough — the explicit
    DEV_LOGIN_ENABLED env opt-in must also be present."""
    monkeypatch.delenv("DEV_LOGIN_ENABLED", raising=False)
    monkeypatch.setitem(app.config, "DEV_LOGIN_ALLOWED", True)

    response = client.get("/api/v1/auth/dev-users")

    assert response.status_code == 403


def test_dev_users_forbidden_outside_dev_config(client, app, monkeypatch):
    """Defense-in-depth: a leaked DEV_LOGIN_ENABLED env var must not open the
    endpoint when the app is not running DevConfig (i.e. stag/prod)."""
    monkeypatch.setenv("DEV_LOGIN_ENABLED", "true")
    monkeypatch.setitem(app.config, "DEV_LOGIN_ALLOWED", False)

    response = client.get("/api/v1/auth/dev-users")

    assert response.status_code == 403
