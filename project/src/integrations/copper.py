"""Copper CRM adapter for leads and opportunities."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class CopperClient:
    def __init__(self, api_key: str | None = None, user_email: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.copper_api_key
        self.user_email = user_email or settings.copper_user_email
        self.base_url = "https://api.copper.com/developer_api/v1"

    def _is_configured(self) -> bool:
        return bool(self.api_key and self.user_email)

    def _headers(self) -> dict:
        return {"X-PW-AccessToken": self.api_key, "X-PW-Application": "developer_api", "X-PW-UserEmail": self.user_email, "Content-Type": "application/json"}

    async def create_lead(self, name: str, email: str = "") -> dict:
        if not self._is_configured():
            return {"id": 1, "name": name, "email": email}
        payload = {"name": name}
        if email:
            payload["email"] = {"email": email, "category": "work"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/leads", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201):
                logger.error("copper_lead_failed", status=resp.status_code)
                return {"id": None, "name": name}
            data = resp.json()
            return {"id": data.get("id"), "name": data.get("name")}
