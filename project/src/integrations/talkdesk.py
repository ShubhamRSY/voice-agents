"""Talkdesk CCaaS adapter for contact and interaction sync."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class TalkdeskClient:
    def __init__(self, api_token: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.api_token = api_token or settings.talkdesk_api_token
        self.base_url = (base_url or settings.talkdesk_base_url or "https://api.talkdeskapp.com").rstrip("/")

    def _is_configured(self) -> bool:
        return bool(self.api_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

    async def create_contact(self, name: str, phone: str, email: str = "") -> dict:
        if not self._is_configured():
            return {"id": "td-mock-001", "name": name, "phone": phone}
        payload = {"name": name, "phones": [{"number": phone}], "emails": [{"email": email}] if email else []}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/contacts", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201):
                logger.error("talkdesk_contact_failed", status=resp.status_code)
                return {"id": None, "name": name}
            data = resp.json()
            return {"id": data.get("id"), "name": name, "phone": phone}
