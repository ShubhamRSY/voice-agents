"""Aircall adapter for call logging and contact sync."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class AircallClient:
    def __init__(self, api_id: str | None = None, api_token: str | None = None):
        settings = get_settings()
        self.api_id = api_id or settings.aircall_api_id
        self.api_token = api_token or settings.aircall_api_token
        self.base_url = "https://api.aircall.io/v1"

    def _is_configured(self) -> bool:
        return bool(self.api_id and self.api_token)

    def _auth(self) -> tuple[str, str]:
        return (self.api_id, self.api_token)

    async def create_contact(self, first_name: str, phone: str, email: str = "") -> dict:
        if not self._is_configured():
            return {"id": 1, "first_name": first_name, "phone": phone}
        payload = {"first_name": first_name, "phone_numbers": [{"value": phone}]}
        if email:
            payload["emails"] = [{"value": email}]
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/contacts", json=payload, auth=self._auth())
            if resp.status_code not in (200, 201):
                logger.error("aircall_contact_failed", status=resp.status_code)
                return {"id": None, "first_name": first_name}
            data = resp.json().get("contact", resp.json())
            return {"id": data.get("id"), "first_name": data.get("first_name")}
