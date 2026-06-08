"""Slack notifications for the apuração workflow (issue #38).

Privacy contract — read this before adding new senders:

  Commission amounts are private. None of the messages emitted by the
  typed `notify_*` functions below contain numerical commission values,
  bonus values, or any other monetary figure. Channel messages mention
  only what changed (period, component, action); DM messages mention
  the period and direct the recipient to the platform.

All sends are graceful: a misconfigured token, missing slack_user_id,
or transport failure logs and returns False without raising — callers
in the state machine must never block a transition on Slack.
"""
import logging
from flask import current_app

from app.models import User, UserRole

logger = logging.getLogger(__name__)


_COMPONENT_LABELS = {
    "ev_quarter": "Comissão EV",
    "ev_quarterly_bonus": "Bônus EV",
    "cn_quarterly_bonus": "Bônus CN",
    "cn_monthly": "Comissão CN",
    "leadership": "Comissão Liderança",
}


def _platform_url(path: str = "") -> str | None:
    base = current_app.config.get("PLATFORM_PUBLIC_URL") or ""
    if not base:
        return None
    return base.rstrip("/") + (path if path.startswith("/") else "/" + path)


def send_slack_dm(user_slack_id, text, blocks=None):
    """Send a Slack DM to a user. Returns False on any failure."""
    token = current_app.config.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not configured, skipping Slack DM")
        return False
    if not user_slack_id:
        logger.info("Slack DM skipped: user has no slack_user_id")
        return False

    try:
        from slack_sdk import WebClient
        client = WebClient(token=token)
        result = client.chat_postMessage(
            channel=user_slack_id,
            text=text,
            blocks=blocks,
        )
        return result["ok"]
    except Exception as e:
        logger.error(f"Slack DM failed: {e}")
        return False


def send_slack_channel(channel_id, text, blocks=None):
    """Send a message to a Slack channel. Returns False on any failure."""
    token = current_app.config.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not configured, skipping Slack message")
        return False
    if not channel_id:
        logger.info("Slack channel send skipped: channel id not configured")
        return False

    try:
        from slack_sdk import WebClient
        client = WebClient(token=token)
        result = client.chat_postMessage(
            channel=channel_id,
            text=text,
            blocks=blocks,
        )
        return result["ok"]
    except Exception as e:
        logger.error(f"Slack channel message failed: {e}")
        return False


def build_appraisal_blocks(title, summary, action_url=None):
    """Build Slack blocks for appraisal notifications."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary},
        },
    ]
    if action_url:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Ver na plataforma"},
                    "url": action_url,
                }
            ],
        })
    return blocks


# ── Helpers ────────────────────────────────────────────────────────────


def _ops_channel():
    return current_app.config.get("SLACK_OPS_CHANNEL")


def _finance_channel():
    return current_app.config.get("SLACK_FINANCE_CHANNEL")


def _period(quarter: int, year: int) -> str:
    return f"Q{quarter}/{year}"


def _period_month(month: int, year: int) -> str:
    return f"{month:02d}/{year}"


def _component_label(component_key: str) -> str:
    return _COMPONENT_LABELS.get(component_key, component_key)


# ── Typed event senders ────────────────────────────────────────────────
#
# Each function emits a single Slack send (or a small fan-out) and never
# raises. Tests assert on the underlying send_slack_* call.


def notify_validating_released(user: User, component_key: str,
                                month: int, year: int) -> bool:
    """DM a user that their component is open for validation."""
    label = _component_label(component_key)
    period = _period_month(month, year)
    text = (
        f"Sua apuração de *{label}* para {period} está disponível para "
        f"validação na plataforma."
    )
    blocks = build_appraisal_blocks(
        title=f"Validação aberta · {label}",
        summary=text,
        action_url=_platform_url("/ev/validation"),
    )
    return send_slack_dm(user.slack_user_id, text, blocks)


def notify_team_validated_for_lider(lider: User, month: int, year: int) -> bool:
    """DM the Líder de Vendas that their team finished validating."""
    period = _period_month(month, year)
    text = (
        f"Seu time concluiu a validação da apuração {period}. "
        f"Você já pode revisar e aprovar."
    )
    blocks = build_appraisal_blocks(
        title=f"Time validou · {period}",
        summary=text,
        action_url=_platform_url("/lider-vendas/dashboard"),
    )
    return send_slack_dm(lider.slack_user_id, text, blocks)


def notify_lider_approved(month: int, year: int, lider_name: str) -> bool:
    """Channel message: Líder aprovou, RevOps revisar."""
    period = _period_month(month, year)
    text = (
        f"{lider_name} aprovou a apuração do time para {period}. "
        f"Pronta para revisão do RevOps."
    )
    blocks = build_appraisal_blocks(
        title=f"Aprovado pelo Líder · {period}",
        summary=text,
        action_url=_platform_url("/admin/apurações"),
    )
    return send_slack_channel(_ops_channel(), text, blocks)


def notify_revops_approved(month: int, year: int) -> bool:
    """Channel message to Finance: RevOps liberou para fechamento."""
    period = _period_month(month, year)
    text = (
        f"A apuração {period} passou pela revisão do RevOps e está "
        f"pronta para o Finance fechar."
    )
    blocks = build_appraisal_blocks(
        title=f"Pronto para Finance · {period}",
        summary=text,
        action_url=_platform_url("/finance/approval"),
    )
    return send_slack_channel(_finance_channel(), text, blocks)


def notify_cycle_locked(quarter: int, year: int) -> bool:
    """Channel + DM each Líder when the QuarterlyCycle reaches LOCKED."""
    period = _period(quarter, year)
    channel_text = f"O ciclo {period} foi fechado. Pagamentos liberados."
    blocks = build_appraisal_blocks(
        title=f"Ciclo fechado · {period}",
        summary=channel_text,
        action_url=_platform_url("/admin/apurações"),
    )
    sent = send_slack_channel(_ops_channel(), channel_text, blocks)

    dm_text = (
        f"O ciclo {period} foi fechado. Os valores do seu time já estão "
        f"disponíveis para conferência na plataforma."
    )
    dm_blocks = build_appraisal_blocks(
        title=f"Ciclo fechado · {period}",
        summary=dm_text,
        action_url=_platform_url("/lider-vendas/dashboard"),
    )
    lideres = User.query.filter_by(
        role=UserRole.LIDER_VENDAS, active=True,
    ).all()
    dm_count = 0
    for lider in lideres:
        if send_slack_dm(lider.slack_user_id, dm_text, dm_blocks):
            dm_count += 1
    logger.info(f"Cycle LOCKED: channel={sent}, DMs sent={dm_count}")
    return sent


def notify_contestation_opened(month: int, year: int,
                                contestant_name: str) -> bool:
    """Channel message in ops: someone contested. No commission value."""
    period = _period_month(month, year)
    text = (
        f"{contestant_name} abriu uma contestação na apuração {period}. "
        f"Detalhes na plataforma."
    )
    blocks = build_appraisal_blocks(
        title=f"Contestação aberta · {period}",
        summary=text,
        action_url=_platform_url("/admin/apurações"),
    )
    return send_slack_channel(_ops_channel(), text, blocks)


def notify_contestation_resolved(contestant: User,
                                  month: int, year: int) -> bool:
    """DM the contestant that their contestation was resolved."""
    period = _period_month(month, year)
    text = (
        f"Sua contestação na apuração {period} foi respondida. "
        f"Confira a devolutiva e re-valide na plataforma."
    )
    blocks = build_appraisal_blocks(
        title=f"Contestação resolvida · {period}",
        summary=text,
        action_url=_platform_url("/ev/validation"),
    )
    return send_slack_dm(contestant.slack_user_id, text, blocks)
