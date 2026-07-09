"""Five9 CCaaS adapter for call disposition and contact sync."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class Five9Client:
    def __init__(self, webhook_url: str | None = None, api_username: str | None = None, api_password: str | None = None):
        settings = get_settings()
        self.webhook_url = webhook_url or settings.five9_webhook_url
        self.api_username = api_username or settings.five9_api_username
        self.api_password = api_password or settings.five9_api_password

    def _is_configured(self) -> bool:
        return bool(self.webhook_url or (self.api_username and self.api_password))

    async def notify_disposition(self, call_id: str, disposition: str, notes: str = "") -> dict:
        if not self._is_configured():
            return {"status": "mock_ok", "call_id": call_id, "disposition": disposition}
        if self.webhook_url:
            payload = {"call_id": call_id, "disposition": disposition, "notes": notes}
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json=payload)
                if resp.status_code not in (200, 201, 202, 204):
                    logger.error("five9_webhook_failed", status=resp.status_code)
                    return {"status": "failed", "call_id": call_id}
                return {"status": "sent", "call_id": call_id, "disposition": disposition}
        return {"status": "mock_ok", "call_id": call_id, "disposition": disposition}
