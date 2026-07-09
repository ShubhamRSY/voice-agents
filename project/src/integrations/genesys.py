"""Genesys Cloud adapter for conversation and callback events."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class GenesysClient:
    def __init__(self, api_key: str | None = None, region: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.genesys_api_key
        self.region = region or settings.genesys_region or "mypurecloud.com"
        self.base_url = f"https://api.{self.region}"

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def create_callback(self, phone: str, name: str = "") -> dict:
        if not self._is_configured():
            return {"id": "genesys-mock-001", "phone": phone, "status": "scheduled"}
        payload = {"callbackNumbers": [phone], "name": name or phone, "routingData": {"queueId": ""}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/api/v2/conversations/callbacks", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201, 202):
                logger.error("genesys_callback_failed", status=resp.status_code)
                return {"id": None, "phone": phone, "status": "failed"}
            data = resp.json()
            return {"id": data.get("id"), "phone": phone, "status": "scheduled"}
