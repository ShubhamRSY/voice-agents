"""8x8 adapter for telephony and contact center notifications."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class EightByEightClient:
    def __init__(self, api_key: str | None = None, webhook_url: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.eight_by_eight_api_key
        self.webhook_url = webhook_url or settings.eight_by_eight_webhook_url

    def _is_configured(self) -> bool:
        return bool(self.api_key or self.webhook_url)

    async def send_notification(self, text: str, title: str = "Nexus") -> dict:
        if not self._is_configured():
            return {"status": "mock_sent", "text": text}
        if self.webhook_url:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json={"title": title, "text": text})
                if resp.status_code not in (200, 201, 202, 204):
                    logger.error("8x8_notify_failed", status=resp.status_code)
                    return {"status": "failed", "text": text}
                return {"status": "sent", "text": text}
        return {"status": "mock_sent", "text": text}
