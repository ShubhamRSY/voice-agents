"""Zoom adapter for meeting links and chatbot notifications."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class ZoomClient:
    def __init__(self, webhook_url: str | None = None, account_id: str | None = None, client_id: str | None = None, client_secret: str | None = None):
        settings = get_settings()
        self.webhook_url = webhook_url or settings.zoom_webhook_url
        self.account_id = account_id or settings.zoom_account_id
        self.client_id = client_id or settings.zoom_client_id
        self.client_secret = client_secret or settings.zoom_client_secret

    def _is_configured(self) -> bool:
        return bool(self.webhook_url or (self.account_id and self.client_id and self.client_secret))

    async def send_notification(self, text: str) -> dict:
        if not self._is_configured():
            return {"status": "mock_sent", "text": text}
        if self.webhook_url:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json={"text": text})
                if resp.status_code not in (200, 201, 202, 204):
                    logger.error("zoom_notify_failed", status=resp.status_code)
                    return {"status": "failed", "text": text}
                return {"status": "sent", "text": text}
        return {"status": "mock_sent", "text": text}
