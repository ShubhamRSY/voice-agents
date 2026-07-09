"""Creatio (bpm'online) adapter for CRM leads."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class CreatioClient:
    def __init__(self, base_url: str | None = None, username: str | None = None, password: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.creatio_base_url).rstrip("/")
        self.username = username or settings.creatio_username
        self.password = password or settings.creatio_password

    def _is_configured(self) -> bool:
        return bool(self.base_url and self.username and self.password)

    async def create_lead(self, name: str, email: str = "") -> dict:
        if not self._is_configured():
            return {"id": "creatio-mock-001", "name": name}
        payload = {"LeadName": name, "Email": email}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/0/ServiceModel/LeadService.svc/CreateLead", json=payload, auth=(self.username, self.password))
            if resp.status_code not in (200, 201):
                logger.error("creatio_lead_failed", status=resp.status_code)
                return {"id": None, "name": name}
            return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"id": "created", "name": name}
