"""Klaviyo adapter for marketing events and profile sync."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class KlaviyoClient:
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.klaviyo_api_key
        self.base_url = "https://a.klaviyo.com/api"

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Klaviyo-API-Key {self.api_key}", "Content-Type": "application/json", "revision": "2024-02-15"}

    async def track_event(self, event_name: str, email: str, properties: dict | None = None) -> dict:
        if not self._is_configured():
            return {"status": "mock_ok", "event": event_name}
        payload = {"data": {"type": "event", "attributes": {"metric": {"data": {"type": "metric", "attributes": {"name": event_name}}}, "profile": {"data": {"type": "profile", "attributes": {"email": email}}}, "properties": properties or {}}}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/events/", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201, 202):
                logger.error("klaviyo_event_failed", status=resp.status_code)
                return {"status": "failed", "event": event_name}
            return {"status": "ok", "event": event_name}
