"""Vonage adapter for SMS and voice notifications."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class VonageClient:
    def __init__(self, api_key: str | None = None, api_secret: str | None = None, from_number: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.vonage_api_key
        self.api_secret = api_secret or settings.vonage_api_secret
        self.from_number = from_number or settings.vonage_from_number

    def _is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    async def send_sms(self, to: str, text: str) -> dict:
        if not self._is_configured():
            return {"status": "mock_sent", "to": to, "text": text}
        payload = {"api_key": self.api_key, "api_secret": self.api_secret, "to": to, "from": self.from_number or "Nexus", "text": text}
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://rest.nexmo.com/sms/json", data=payload)
            if resp.status_code != 200:
                logger.error("vonage_sms_failed", status=resp.status_code)
                return {"status": "failed", "to": to}
            data = resp.json().get("messages", [{}])[0]
            return {"status": data.get("status"), "to": to, "message_id": data.get("message-id")}
