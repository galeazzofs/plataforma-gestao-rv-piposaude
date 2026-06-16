"""Google SSO hardening: domain list, case handling, verified_email, timeouts."""
import pytest

from app.auth import google_sso
from app.auth.google_sso import (
    GoogleSSOError,
    exchange_code_for_tokens,
    get_user_info,
    validate_email_domain,
)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(payload)

    def json(self):
        return self._payload


# ── validate_email_domain ────────────────────────────────────────────


def test_accepts_both_pipo_domains(app):
    # Real users exist under both registrations of the company domain.
    assert validate_email_domain("ana@piposaude.com") is True
    assert validate_email_domain("fernando@piposaude.com.br") is True


def test_domain_check_is_case_insensitive(app):
    assert validate_email_domain("ANA@PIPOSAUDE.COM") is True


def test_rejects_foreign_domains(app):
    with pytest.raises(GoogleSSOError):
        validate_email_domain("attacker@gmail.com")
    # Suffix tricks must not pass either.
    with pytest.raises(GoogleSSOError):
        validate_email_domain("attacker@evilpiposaude.com")


def test_allowed_domains_config_override(app, monkeypatch):
    monkeypatch.setitem(app.config, "ALLOWED_EMAIL_DOMAINS", ["example.com"])
    assert validate_email_domain("x@example.com") is True
    with pytest.raises(GoogleSSOError):
        validate_email_domain("x@piposaude.com")


# ── get_user_info: verified_email is mandatory ───────────────────────


def test_user_info_rejects_unverified_email(app, monkeypatch):
    monkeypatch.setattr(
        google_sso.requests,
        "get",
        lambda *a, **k: _FakeResponse(200, {"email": "x@piposaude.com", "verified_email": False}),
    )
    with pytest.raises(GoogleSSOError):
        get_user_info("token")


def test_user_info_rejects_missing_verified_flag(app, monkeypatch):
    monkeypatch.setattr(
        google_sso.requests,
        "get",
        lambda *a, **k: _FakeResponse(200, {"email": "x@piposaude.com"}),
    )
    with pytest.raises(GoogleSSOError):
        get_user_info("token")


def test_user_info_accepts_verified_email(app, monkeypatch):
    monkeypatch.setattr(
        google_sso.requests,
        "get",
        lambda *a, **k: _FakeResponse(200, {"email": "x@piposaude.com", "verified_email": True}),
    )
    info = get_user_info("token")
    assert info["email"] == "x@piposaude.com"


# ── network calls must carry timeouts ────────────────────────────────


def test_token_exchange_sends_timeout(app, monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse(200, {"access_token": "t"})

    monkeypatch.setattr(google_sso.requests, "post", fake_post)
    exchange_code_for_tokens("code")
    assert captured.get("timeout"), "requests.post must set an explicit timeout"


def test_user_info_sends_timeout(app, monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse(200, {"email": "x@piposaude.com", "verified_email": True})

    monkeypatch.setattr(google_sso.requests, "get", fake_get)
    get_user_info("token")
    assert captured.get("timeout"), "requests.get must set an explicit timeout"
