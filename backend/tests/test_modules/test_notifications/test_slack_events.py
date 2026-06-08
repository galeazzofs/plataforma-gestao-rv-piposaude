"""Slack event notification tests with mocked client (issue #38)."""
from decimal import Decimal
import uuid
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models import User, UserRole
from app.modules.notifications import slack as slack_module


@pytest.fixture(autouse=True)
def configure_slack(app):
    """Inject a fake bot token + channels so the senders don't short-circuit."""
    app.config["SLACK_BOT_TOKEN"] = "xoxb-test"
    app.config["SLACK_OPS_CHANNEL"] = "#ops-channel"
    app.config["SLACK_FINANCE_CHANNEL"] = "#finance-channel"
    app.config["PLATFORM_PUBLIC_URL"] = "https://platform.example.com"
    yield
    app.config["SLACK_BOT_TOKEN"] = ""
    app.config["SLACK_OPS_CHANNEL"] = ""
    app.config["SLACK_FINANCE_CHANNEL"] = ""
    app.config["PLATFORM_PUBLIC_URL"] = ""


def _user(role, name="Test User", slack_id="U123"):
    suffix = uuid.uuid4().hex[:6]
    u = User(
        email=f"{name.lower().replace(' ', '_')}-{suffix}@x",
        name=name, role=role, active=True,
        slack_user_id=slack_id,
    )
    db.session.add(u)
    db.session.flush()
    return u


def _capture_calls():
    """Patch slack_sdk.WebClient.chat_postMessage and return the mock."""
    mock = MagicMock(return_value={"ok": True})
    return patch("slack_sdk.WebClient.chat_postMessage", mock), mock


def test_validating_released_dms_user(db_session):
    user = _user(UserRole.EV, "Joana", slack_id="U-EV-1")

    ctx, mock = _capture_calls()
    with ctx:
        ok = slack_module.notify_validating_released(user, "ev_quarter", 1, 2030)

    assert ok is True
    assert mock.called
    kwargs = mock.call_args.kwargs
    assert kwargs["channel"] == "U-EV-1"
    assert "Comissão EV" in kwargs["text"]
    assert "01/2030" in kwargs["text"]
    # Privacy contract: no R$ or numeric commission value in the body
    assert "R$" not in kwargs["text"]


def test_team_validated_for_lider_dms_lider(db_session):
    lider = _user(UserRole.LIDER_VENDAS, "Carla", slack_id="U-LIDER-1")

    ctx, mock = _capture_calls()
    with ctx:
        slack_module.notify_team_validated_for_lider(lider, 2, 2030)

    kwargs = mock.call_args.kwargs
    assert kwargs["channel"] == "U-LIDER-1"
    assert "02/2030" in kwargs["text"]


def test_lider_approved_posts_to_ops_channel(db_session):
    ctx, mock = _capture_calls()
    with ctx:
        slack_module.notify_lider_approved(3, 2030, "Carla Silva")

    kwargs = mock.call_args.kwargs
    assert kwargs["channel"] == "#ops-channel"
    assert "Carla Silva" in kwargs["text"]
    assert "03/2030" in kwargs["text"]
    assert "R$" not in kwargs["text"]


def test_revops_approved_posts_to_finance_channel(db_session):
    ctx, mock = _capture_calls()
    with ctx:
        slack_module.notify_revops_approved(4, 2030)

    kwargs = mock.call_args.kwargs
    assert kwargs["channel"] == "#finance-channel"
    assert "04/2030" in kwargs["text"]


def test_contestation_opened_omits_value(db_session):
    ctx, mock = _capture_calls()
    with ctx:
        slack_module.notify_contestation_opened(1, 2030, "Pedro")

    kwargs = mock.call_args.kwargs
    assert kwargs["channel"] == "#ops-channel"
    assert "Pedro" in kwargs["text"]
    assert "01/2030" in kwargs["text"]
    assert "R$" not in kwargs["text"]


def test_contestation_resolved_dms_contestant(db_session):
    user = _user(UserRole.EV, "Pedro", slack_id="U-PEDRO")
    ctx, mock = _capture_calls()
    with ctx:
        slack_module.notify_contestation_resolved(user, 1, 2030)

    kwargs = mock.call_args.kwargs
    assert kwargs["channel"] == "U-PEDRO"
    assert "01/2030" in kwargs["text"]


def test_cycle_locked_fans_out_to_channel_and_lideres(db_session):
    a = _user(UserRole.LIDER_VENDAS, "LiderA", slack_id="U-A")
    b = _user(UserRole.LIDER_VENDAS, "LiderB", slack_id="U-B")
    ctx, mock = _capture_calls()
    with ctx:
        slack_module.notify_cycle_locked(2, 2030)

    channels = [c.kwargs["channel"] for c in mock.call_args_list]
    assert "#ops-channel" in channels
    assert "U-A" in channels
    assert "U-B" in channels
    for c in mock.call_args_list:
        assert "R$" not in c.kwargs["text"]


def test_send_dm_skips_when_no_slack_id(db_session):
    user = _user(UserRole.EV, "Sem Slack", slack_id=None)
    ctx, mock = _capture_calls()
    with ctx:
        ok = slack_module.notify_validating_released(user, "ev_quarter", 1, 2030)
    assert ok is False
    assert not mock.called


def test_send_channel_skips_when_channel_missing(db_session, app):
    app.config["SLACK_OPS_CHANNEL"] = ""
    ctx, mock = _capture_calls()
    with ctx:
        ok = slack_module.notify_lider_approved(1, 2030, "X")
    assert ok is False
    assert not mock.called


def test_send_failure_does_not_raise(db_session):
    user = _user(UserRole.EV, "Falha", slack_id="U-F")
    bad_mock = MagicMock(side_effect=Exception("Slack down"))
    with patch("slack_sdk.WebClient.chat_postMessage", bad_mock):
        ok = slack_module.notify_validating_released(user, "ev_quarter", 1, 2030)
    assert ok is False
