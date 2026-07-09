"""Microsoft Dynamics 365 adapter for CRM cases and contacts."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class Dynamics365Client:
    def __init__(self, instance_url: str | None = None, access_token: str | None = None):
        settings = get_settings()
        self.instance_url = (instance_url or settings.dynamics_instance_url).rstrip("/")
        self.access_token = access_token or settings.dynamics_access_token

    def _is_configured(self) -> bool:
        return bool(self.instance_url and self.access_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "OData-MaxVersion": "4.0"}

    async def create_case(self, title: str, description: str = "") -> dict:
        if not self._is_configured():
            return {"id": "dyn-mock-001", "title": title, "status": "active"}
        payload = {"title": title, "description": description}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.instance_url}/api/data/v9.2/incidents", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201, 204):
                logger.error("dynamics_case_failed", status=resp.status_code)
                return {"id": None, "title": title, "status": "failed"}
            return {"id": resp.headers.get("OData-EntityId", "created"), "title": title, "status": "active"}
