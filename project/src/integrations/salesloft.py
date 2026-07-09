"""Salesloft adapter for sales engagement cadences."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class SalesloftClient:
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.salesloft_api_key
        self.base_url = "https://api.salesloft.com/v2"

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def create_person(self, email: str, first_name: str = "", last_name: str = "") -> dict:
        if not self._is_configured():
            return {"id": 1, "email": email}
        payload = {"email_address": email, "first_name": first_name, "last_name": last_name}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/people.json", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201):
                logger.error("salesloft_person_failed", status=resp.status_code)
                return {"id": None, "email": email}
            data = resp.json().get("data", {})
            return {"id": data.get("id"), "email": email}
