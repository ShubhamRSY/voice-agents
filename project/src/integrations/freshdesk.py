"""Freshdesk adapter for help desk ticket management."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class FreshdeskClient:
    def __init__(self, domain: str | None = None, api_key: str | None = None):
        settings = get_settings()
        self.domain = domain or settings.freshdesk_domain
        self.api_key = api_key or settings.freshdesk_api_key
        self.base_url = f"https://{self.domain}.freshdesk.com/api/v2"

    def _is_configured(self) -> bool:
        return bool(self.domain and self.api_key)

    def _auth(self) -> tuple[str, str]:
        return (self.api_key, "X")

    async def create_ticket(self, subject: str, description: str, email: str = "", priority: int = 2) -> dict:
        if not self._is_configured():
            return {"id": 1, "subject": subject, "priority": priority, "status": "open"}

        payload = {
            "subject": subject,
            "description": description,
            "priority": priority,
            "status": 2,
        }
        if email:
            payload["email"] = email

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/tickets",
                json=payload,
                auth=self._auth(),
            )
            if resp.status_code not in (200, 201):
                logger.error("freshdesk_ticket_failed", status=resp.status_code)
                return {"id": None, "subject": subject, "status": "failed"}
            data = resp.json()
            return {"id": data.get("id"), "subject": data.get("subject"), "status": data.get("status")}

    async def get_contact(self, email: str) -> dict | None:
        if not self._is_configured():
            return {"id": 1, "email": email, "name": "Mock Contact"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/contacts",
                params={"email": email},
                auth=self._auth(),
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data[0] if data else None
