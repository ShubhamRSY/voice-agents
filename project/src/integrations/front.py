"""Front adapter for team inboxes and conversation routing."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class FrontClient:
    def __init__(self, api_token: str | None = None, channel_id: str | None = None):
        settings = get_settings()
        self.api_token = api_token or settings.front_api_token
        self.channel_id = channel_id or settings.front_channel_id
        self.base_url = "https://api2.frontapp.com"

    def _is_configured(self) -> bool:
        return bool(self.api_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

    async def create_message(self, subject: str, body: str, to: str) -> dict:
        if not self._is_configured():
            return {"id": "front-mock-001", "subject": subject, "status": "sent"}

        if not self.channel_id:
            return {"id": None, "subject": subject, "status": "failed", "error": "channel_id_required"}

        payload = {
            "to": [to],
            "subject": subject,
            "body": body,
            "options": {"archive": False},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/channels/{self.channel_id}/messages",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201, 202):
                logger.error("front_message_failed", status=resp.status_code)
                return {"id": None, "subject": subject, "status": "failed"}
            data = resp.json()
            return {"id": data.get("id"), "subject": subject, "status": "sent"}
