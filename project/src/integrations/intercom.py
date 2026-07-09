"""Intercom adapter for customer messaging and support."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class IntercomClient:
    def __init__(self, access_token: str | None = None):
        settings = get_settings()
        self.access_token = access_token or settings.intercom_access_token

    def _is_configured(self) -> bool:
        return bool(self.access_token)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_conversation(self, subject: str, body: str, email: str) -> dict:
        if not self._is_configured():
            return {"id": "conv-mock-001", "subject": subject, "state": "open"}

        payload = {
            "from": {"type": "contact", "email": email},
            "body": f"<p>{body}</p>",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.intercom.io/conversations",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("intercom_conversation_failed", status=resp.status_code)
                return {"id": None, "subject": subject, "state": "failed"}
            data = resp.json()
            return {"id": data.get("id"), "subject": subject, "state": data.get("state", "open")}

    async def search_contact(self, email: str) -> dict | None:
        if not self._is_configured():
            return {"id": "contact-mock-001", "email": email}
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.intercom.io/contacts/search",
                json={"query": {"field": "email", "operator": "=", "value": email}},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data["data"][0] if data.get("data") else None
