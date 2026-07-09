"""Ujet CCaaS adapter for session and callback management."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class UjetClient:
    def __init__(self, api_key: str | None = None, subdomain: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.ujet_api_key
        self.subdomain = subdomain or settings.ujet_subdomain
        self.base_url = f"https://{self.subdomain}.ujet.co/api/v2" if self.subdomain else ""

    def _is_configured(self) -> bool:
        return bool(self.api_key and self.subdomain)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def schedule_callback(self, phone: str, reason: str = "") -> dict:
        if not self._is_configured():
            return {"id": "ujet-mock-001", "phone": phone, "status": "scheduled"}
        payload = {"phone_number": phone, "reason": reason or "Nexus callback"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/callbacks", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201, 202):
                logger.error("ujet_callback_failed", status=resp.status_code)
                return {"id": None, "phone": phone, "status": "failed"}
            data = resp.json()
            return {"id": data.get("id"), "phone": phone, "status": "scheduled"}
