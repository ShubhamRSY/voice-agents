"""RingCentral adapter for telephony notifications via webhook."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class RingCentralClient:
    def __init__(self, webhook_url: str | None = None):
        settings = get_settings()
        self.webhook_url = webhook_url or settings.ringcentral_webhook_url

    def _is_configured(self) -> bool:
        return bool(self.webhook_url)

    async def send_notification(self, text: str, title: str = "Nexus alert") -> dict:
        if not self._is_configured():
            return {"status": "mock_sent", "text": text}

        payload = {"title": title, "text": text}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self.webhook_url, json=payload)
            if resp.status_code not in (200, 201, 202, 204):
                logger.error("ringcentral_notify_failed", status=resp.status_code)
                return {"status": "failed", "text": text}
            return {"status": "sent", "text": text}
