"""NiCE CXone adapter for contact center interactions."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class NiceClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.nice_api_key
        self.base_url = (base_url or settings.nice_base_url or "https://api-c32.nice-incontact.com").rstrip("/")

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def create_contact(self, phone: str, skill_id: str = "") -> dict:
        if not self._is_configured():
            return {"id": "nice-mock-001", "phone": phone, "status": "queued"}
        payload = {"phoneNumber": phone, "skillId": skill_id or None}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/incontactapi/services/v23.0/contacts", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201, 202):
                logger.error("nice_contact_failed", status=resp.status_code)
                return {"id": None, "phone": phone, "status": "failed"}
            data = resp.json()
            return {"id": data.get("contactId"), "phone": phone, "status": "queued"}
