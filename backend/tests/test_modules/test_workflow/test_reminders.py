"""Reminder + escalation tests with mocked clock + Slack (issue #39)."""
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
import uuid
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models import (
    AppraisalStatus, CnMonthlyAppraisal, LiderVendasQuarterAppraisal,
    Team, User, UserRole,
)
from app.modules.workflow import reminders as reminders_module


@pytest.fixture(autouse=True)
def configure_slack(app):
    app.config["SLACK_BOT_TOKEN"] = "xoxb-test"
    app.config["SLACK_OPS_CHANNEL"] = "#ops-channel"
    yield
    app.config["SLACK_BOT_TOKEN"] = ""
    app.config["SLACK_OPS_CHANNEL"] = ""


def _user(role, name, slack_id=None, team_id=None):
    suffix = uuid.uuid4().hex[:6]
    u = User(
        email=f"{name.lower().replace(' ', '_')}-{suffix}@x",
        name=name, role=role, active=True,
        slack_user_id=slack_id, team_id=team_id,
    )
    db.session.add(u)
    db.session.flush()
    return u


def _cn_appraisal(cn, status, last_action_at, month=4, year=2030):
    a = CnMonthlyAppraisal(
        cn_id=cn.id, month=month, year=year,
        sao_realizado=Decimal("0"), vidas_realizado=Decimal("0"),
        pct_sao=Decimal("0"), pct_vidas=Decimal("0"),
        score_final=Decimal("0"), multiplicador=Decimal("0"),
        commission_amount=Decimal("0"),
        status=status,
        last_action_at=last_action_at,
    )
    db.session.add(a)
    db.session.flush()
    return a


def _patch_clock(now):
    return patch.object(reminders_module, "_now", return_value=now)


def _capture_slack():
    mock = MagicMock(return_value={"ok": True})
    return patch("slack_sdk.WebClient.chat_postMessage", mock), mock


def test_no_reminder_before_2_days(db_session):
    cn = _user(UserRole.CN, "Aline", slack_id="U-CN-A")
    now = datetime(2030, 6, 1, 12, tzinfo=timezone.utc)
    _cn_appraisal(cn, AppraisalStatus.VALIDATING, now - timedelta(days=1))

    ctx, mock = _capture_slack()
    with _patch_clock(now), ctx:
        result = reminders_module.check_pending_validations()
    assert result["reminders_sent"] == 0
    assert not mock.called


def test_reminder_fires_after_2_days(db_session):
    cn = _user(UserRole.CN, "Bruno", slack_id="U-CN-B")
    now = datetime(2030, 6, 5, 12, tzinfo=timezone.utc)
    _cn_appraisal(cn, AppraisalStatus.VALIDATING, now - timedelta(days=3))

    ctx, mock = _capture_slack()
    with _patch_clock(now), ctx:
        result = reminders_module.check_pending_validations()
    assert result["reminders_sent"] == 1
    assert any(c.kwargs["channel"] == "U-CN-B" for c in mock.call_args_list)


def test_reminder_does_not_repeat_same_day(db_session):
    cn = _user(UserRole.CN, "Cris", slack_id="U-CN-C")
    now = datetime(2030, 6, 5, 12, tzinfo=timezone.utc)
    a = _cn_appraisal(cn, AppraisalStatus.VALIDATING, now - timedelta(days=3))
    a.reminder_sent_at = now.date()
    db.session.flush()

    ctx, mock = _capture_slack()
    with _patch_clock(now), ctx:
        result = reminders_module.check_pending_validations()
    assert result["reminders_sent"] == 0


def test_escalation_after_7_days(db_session):
    cn = _user(UserRole.CN, "Diego", slack_id="U-CN-D")
    now = datetime(2030, 6, 12, 12, tzinfo=timezone.utc)
    _cn_appraisal(cn, AppraisalStatus.VALIDATING, now - timedelta(days=8))

    ctx, mock = _capture_slack()
    with _patch_clock(now), ctx:
        result = reminders_module.check_pending_validations()
    assert result["reminders_sent"] == 1
    assert result["escalations"] == 1
    # Channel send to ops + DM to user
    channels = [c.kwargs["channel"] for c in mock.call_args_list]
    assert "#ops-channel" in channels
    assert "U-CN-D" in channels


def test_recipient_for_lider_review_is_team_leader(db_session):
    lider = _user(UserRole.LIDER_VENDAS, "Líder X", slack_id="U-LIDER-X")
    team = Team(name=f"Time-{uuid.uuid4().hex[:5]}", leader_id=lider.id)
    db.session.add(team)
    db.session.flush()
    cn = _user(UserRole.CN, "Membro Y", slack_id="U-CN-Y", team_id=team.id)
    now = datetime(2030, 6, 5, 12, tzinfo=timezone.utc)
    _cn_appraisal(cn, AppraisalStatus.LIDER_REVIEW, now - timedelta(days=3))

    ctx, mock = _capture_slack()
    with _patch_clock(now), ctx:
        reminders_module.check_pending_validations()

    channels = [c.kwargs["channel"] for c in mock.call_args_list]
    # The Líder gets the DM, not the CN
    assert "U-LIDER-X" in channels
    assert "U-CN-Y" not in channels


def test_lider_appraisal_reminder(db_session):
    lider = _user(UserRole.LIDER_VENDAS, "Lider-Z", slack_id="U-LIDER-Z")
    now = datetime(2030, 6, 5, 12, tzinfo=timezone.utc)
    db.session.add(LiderVendasQuarterAppraisal(
        lider_vendas_id=lider.id, quarter=2, year=2030,
        meta_mrr=Decimal("0"), meta_sql=0,
        realizado_mrr=Decimal("0"), realizado_sql=0,
        pct_mrr=Decimal("0"), pct_sql=Decimal("0"),
        multiplicador=Decimal("0"), bonus_amount=Decimal("0"),
        status=AppraisalStatus.VALIDATING,
        last_action_at=now - timedelta(days=4),
    ))
    db.session.flush()

    ctx, mock = _capture_slack()
    with _patch_clock(now), ctx:
        result = reminders_module.check_pending_validations()
    assert result["reminders_sent"] == 1
    assert any(c.kwargs["channel"] == "U-LIDER-Z" for c in mock.call_args_list)


def test_transition_clears_reminder_state(db_session):
    """A re-action zeroes last_action_at and reminder_sent_at, so the
    timer starts over cleanly."""
    from app.modules.workflow.state_machine import (
        transition_cn_monthly_appraisal,
    )
    cn = _user(UserRole.CN, "Reset", slack_id="U-CN-R")
    old = datetime(2020, 1, 1, 12, tzinfo=timezone.utc)
    a = _cn_appraisal(cn, AppraisalStatus.VALIDATING, old)
    a.reminder_sent_at = date(2020, 1, 5)
    db.session.flush()

    transition_cn_monthly_appraisal(a, AppraisalStatus.LIDER_REVIEW)
    assert a.last_action_at is not None
    assert a.last_action_at > old
    assert a.reminder_sent_at is None
