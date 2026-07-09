"""Microsoft Teams adapter for channel notifications and alerts."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class TeamsClient:
    def __init__(self, webhook_url: str | None = None):
        settings = get_settings()
        self.webhook_url = webhook_url or settings.teams_webhook_url

    def _is_configured(self) -> bool:
        return bool(self.webhook_url)

    async def send_message(self, text: str, title: str = "") -> dict:
        if not self._is_configured():
            logger.info("teams_mock", text=text[:80])
            return {"status": "mock_sent", "text": text}

        payload: dict = {"text": text}
        if title:
            payload = {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "summary": title,
                "themeColor": "0078D4",
                "title": title,
                "text": text,
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.webhook_url, json=payload)
            if resp.status_code not in (200, 201, 202):
                logger.error("teams_message_failed", status=resp.status_code)
                return {"status": "failed", "text": text}
            return {"status": "sent", "text": text}

    async def notify_escalation(self, session_id: str, customer: str, summary: str) -> dict:
        text = f"**Escalation** — Session `{session_id}`\n\nCustomer: {customer}\n\n{summary}"
        return await self.send_message(text, title="Nexus escalation")
