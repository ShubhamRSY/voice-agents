"""Dialpad adapter for call center SMS and disposition sync."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class DialpadClient:
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.dialpad_api_key
        self.base_url = "https://dialpad.com/api/v2"

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def send_sms(self, to: str, text: str) -> dict:
        if not self._is_configured():
            return {"status": "mock_sent", "to": to}
        payload = {"to_numbers": [to], "text": text}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/sms", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201, 202):
                logger.error("dialpad_sms_failed", status=resp.status_code)
                return {"status": "failed", "to": to}
            return {"status": "sent", "to": to, "data": resp.json()}
