import logging
from flask import current_app

logger = logging.getLogger(__name__)


def send_slack_dm(user_slack_id, text, blocks=None):
    """Send a Slack DM to a user."""
    token = current_app.config.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not configured, skipping Slack DM")
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
    """Send a message to a Slack channel."""
    token = current_app.config.get("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("SLACK_BOT_TOKEN not configured, skipping Slack message")
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
