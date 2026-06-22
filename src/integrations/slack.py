"""Slack integration for agent handoff notifications and escalation alerts."""

from typing import Any

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class SlackNotifier:
    def __init__(self, webhook_url: str | None = None):
        settings = get_settings()
        self.webhook_url = webhook_url or settings.slack_webhook_url

    def _is_configured(self) -> bool:
        return bool(self.webhook_url)

    async def send_alert(self, channel: str, text: str, blocks: list[dict] | None = None) -> dict:
        if not self._is_configured():
            logger.info("slack_mock", channel=channel, text=text[:60])
            return {"status": "mock_sent", "channel": channel}

        payload: dict[str, Any] = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.webhook_url, json=payload)
            if resp.status_code != 200:
                logger.error("slack_failed", status=resp.status_code)
                return {"status": "failed", "error": str(resp.status_code)}
            return {"status": "sent", "channel": channel}

    async def notify_escalation(self, session_id: str, customer: str, reason: str, agent: str = "AI Agent") -> dict:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 Escalation Required"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Session:*\n{session_id}"},
                    {"type": "mrkdwn", "text": f"*Customer:*\n{customer}"},
                    {"type": "mrkdwn", "text": f"*Agent:*\n{agent}"},
                    {"type": "mrkdwn", "text": f"*Reason:*\n{reason}"},
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Conversation"},
                        "url": f"http://localhost:8000/?session={session_id}",
                    }
                ],
            },
        ]
        return await self.send_alert("#escalations", text=f"Escalation: {customer} - {reason}", blocks=blocks)

    async def notify_ticket_created(self, ticket_id: str, subject: str, customer: str, provider: str) -> dict:
        blocks = [
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Ticket Created:*\n<http://localhost:8000|{ticket_id}>"},
                    {"type": "mrkdwn", "text": f"*Subject:*\n{subject}"},
                    {"type": "mrkdwn", "text": f"*Customer:*\n{customer}"},
                    {"type": "mrkdwn", "text": f"*Provider:*\n{provider}"},
                ],
            }
        ]
        return await self.send_alert("#tickets", text=f"Ticket {ticket_id}: {subject}", blocks=blocks)

    async def notify_agent_handoff(self, session_id: str, customer: str, summary: str) -> dict:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "👋 Human Agent Handoff"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Session:*\n{session_id}"},
                    {"type": "mrkdwn", "text": f"*Customer:*\n{customer}"},
                ],
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Summary:*\n{summary[:500]}"}},
        ]
        return await self.send_alert("#agent-handoff", text=f"Handoff: {customer}", blocks=blocks)

    async def notify_metric_alert(self, metric: str, value: float, threshold: float) -> dict:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *Metric Alert:* {metric} is {value} (threshold: {threshold})",
                },
            }
        ]
        return await self.send_alert("#alerts", text=f"Alert: {metric}={value}", blocks=blocks)


slack = SlackNotifier()
