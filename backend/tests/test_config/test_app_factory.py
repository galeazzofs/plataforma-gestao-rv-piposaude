"""create_app must fail closed on environment selection.

A deploy that forgets FLASK_ENV must refuse to boot instead of silently
loading DevConfig (whose SECRET_KEY falls back to a repo-public value,
making every JWT forgeable).
"""
import pytest

from app import create_app


def test_create_app_requires_flask_env(monkeypatch):
    monkeypatch.delenv("FLASK_ENV", raising=False)
    with pytest.raises(RuntimeError, match="FLASK_ENV"):
        create_app()


def test_create_app_rejects_unknown_flask_env(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")  # typo of "prod"
    with pytest.raises(RuntimeError, match="production"):
        create_app()


def test_create_app_with_explicit_config_name_still_works():
    app = create_app("test")
    assert app.config["TESTING"] is True
