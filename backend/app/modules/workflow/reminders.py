"""Idle-component reminders + escalations (issue #39).

The cron job below scans CnMonthlyAppraisal and LiderVendasQuarterAppraisal
rows that are sitting in VALIDATING or LIDER_REVIEW for too long and
fires a Slack DM after 2 days, escalating to the ops channel after 7.

Time accounting:
  - last_action_at is bumped by every transition (state_machine.py).
  - reminder_sent_at is the date of the most recent DM. It avoids
    re-DMing a recipient several times per day.

Both fields reset to None on a new transition, so a re-validation or
contestation zeros the timer cleanly.
"""
import logging
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import (
    AppraisalStatus, CnMonthlyAppraisal, LiderVendasQuarterAppraisal, User,
)
from app.modules.notifications import slack as slack_module

logger = logging.getLogger(__name__)


REMINDER_DAYS = 2
ESCALATION_DAYS = 7

_PENDING_STATUSES = (
    AppraisalStatus.VALIDATING,
    AppraisalStatus.LIDER_REVIEW,
)


def _now() -> datetime:
    """Indirection so tests can monkeypatch the clock."""
    return datetime.now(timezone.utc)


def _idle_for(appraisal, now: datetime) -> timedelta | None:
    if appraisal.last_action_at is None:
        return None
    last = appraisal.last_action_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last


def _recipient_for_cn(appraisal: CnMonthlyAppraisal):
    if appraisal.status == AppraisalStatus.VALIDATING:
        return db.session.get(User, appraisal.cn_id)
    if appraisal.status == AppraisalStatus.LIDER_REVIEW:
        cn = db.session.get(User, appraisal.cn_id)
        if cn is None or cn.team_id is None:
            return None
        from app.models import Team
        team = db.session.get(Team, cn.team_id)
        if team is None or team.leader_id is None:
            return None
        return db.session.get(User, team.leader_id)
    return None


def _recipient_for_lider(appraisal: LiderVendasQuarterAppraisal):
    return db.session.get(User, appraisal.lider_vendas_id)


def _component_label_cn():
    return "Comissão CN"


def _component_label_lider():
    return "Comissão Liderança"


def _send_reminder_dm(user: User, label: str, period: str):
    if user is None:
        return False
    text = (
        f"Lembrete: sua *{label}* de {period} ainda está esperando sua "
        f"ação na plataforma."
    )
    blocks = slack_module.build_appraisal_blocks(
        title=f"Lembrete · {label}",
        summary=text,
        action_url=None,
    )
    return slack_module.send_slack_dm(user.slack_user_id, text, blocks)


def _send_escalation(channel_text: str):
    from flask import current_app
    ops = current_app.config.get("SLACK_OPS_CHANNEL")
    blocks = slack_module.build_appraisal_blocks(
        title="Escalation · 7 dias parados",
        summary=channel_text,
        action_url=None,
    )
    return slack_module.send_slack_channel(ops, channel_text, blocks)


def check_pending_validations() -> dict:
    """Daily cron: emit reminders + collect escalations.

    Returns a summary dict with counts (useful for tests + logs).
    """
    now = _now()
    today = now.date()
    reminder_threshold = now - timedelta(days=REMINDER_DAYS)
    escalation_threshold = now - timedelta(days=ESCALATION_DAYS)

    summary = {
        "reminders_sent": 0,
        "escalations": 0,
        "scanned": 0,
    }
    escalation_lines: list[str] = []

    cn_rows = CnMonthlyAppraisal.query.filter(
        CnMonthlyAppraisal.status.in_(_PENDING_STATUSES),
        CnMonthlyAppraisal.last_action_at.isnot(None),
        CnMonthlyAppraisal.last_action_at <= reminder_threshold,
    ).all()
    for row in cn_rows:
        summary["scanned"] += 1
        idle = _idle_for(row, now)
        if idle is None:
            continue
        recipient = _recipient_for_cn(row)
        period = f"{row.month:02d}/{row.year}"
        # 7-day escalation
        if row.last_action_at <= escalation_threshold:
            label = (
                f"Comissão CN {period} parada há {idle.days} dias em "
                f"{row.status.value}"
            )
            if recipient is not None:
                label += f" (responsável: {recipient.name})"
            escalation_lines.append(label)
        # 2-day reminder, max once a day
        if row.reminder_sent_at == today:
            continue
        sent = _send_reminder_dm(recipient, _component_label_cn(), period)
        if sent:
            row.reminder_sent_at = today
            summary["reminders_sent"] += 1

    lv_rows = LiderVendasQuarterAppraisal.query.filter(
        LiderVendasQuarterAppraisal.status.in_(_PENDING_STATUSES),
        LiderVendasQuarterAppraisal.last_action_at.isnot(None),
        LiderVendasQuarterAppraisal.last_action_at <= reminder_threshold,
    ).all()
    for row in lv_rows:
        summary["scanned"] += 1
        idle = _idle_for(row, now)
        if idle is None:
            continue
        recipient = _recipient_for_lider(row)
        period = f"Q{row.quarter}/{row.year}"
        if row.last_action_at <= escalation_threshold:
            label = (
                f"Comissão Liderança {period} parada há {idle.days} dias em "
                f"{row.status.value}"
            )
            if recipient is not None:
                label += f" (responsável: {recipient.name})"
            escalation_lines.append(label)
        if row.reminder_sent_at == today:
            continue
        sent = _send_reminder_dm(recipient, _component_label_lider(), period)
        if sent:
            row.reminder_sent_at = today
            summary["reminders_sent"] += 1

    if escalation_lines:
        body = "Componentes parados há mais de 7 dias:\n" + "\n".join(
            f"• {line}" for line in escalation_lines
        )
        ok = _send_escalation(body)
        if ok:
            summary["escalations"] = len(escalation_lines)

    db.session.flush()
    logger.info(f"check_pending_validations: {summary}")
    return summary
