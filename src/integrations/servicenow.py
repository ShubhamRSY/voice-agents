"""ServiceNow adapter for incident/request management."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class ServiceNowClient:
    def __init__(self, instance: str | None = None, api_key: str | None = None):
        settings = get_settings()
        self.instance = instance or settings.servicenow_instance
        self.api_key = api_key or settings.servicenow_api_key
        self.base_url = f"https://{self.instance}.service-now.com"

    def _is_configured(self) -> bool:
        return bool(self.instance and self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def create_incident(self, short_description: str, description: str, caller_email: str = "") -> dict:
        if not self._is_configured():
            return {"id": "INC0010001", "short_description": short_description, "state": "new"}

        payload = {
            "short_description": short_description,
            "description": description,
            "caller_id": caller_email,
            "contact_type": "chat",
            "category": "inquiry",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/now/table/incident",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("servicenow_incident_failed", status=resp.status_code)
                return {"id": "error", "short_description": short_description, "state": "failed"}
            data = resp.json().get("result", {})
            return {
                "id": data.get("sys_id", ""),
                "number": data.get("number", ""),
                "short_description": short_description,
                "state": data.get("state", "1"),
            }

    async def create_request(self, description: str, requested_for: str = "") -> dict:
        if not self._is_configured():
            return {"id": "REQ0010001", "description": description, "state": "new"}

        payload = {"description": description, "requested_for": requested_for}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/now/table/sc_request",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("servicenow_request_failed", status=resp.status_code)
                return {"id": "error", "description": description, "state": "failed"}
            data = resp.json().get("result", {})
            return {"id": data.get("sys_id", ""), "description": description, "state": data.get("state", "1")}

    async def update_incident(self, incident_id: str, fields: dict) -> dict:
        if not self._is_configured():
            return {"id": incident_id, **fields}

        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{self.base_url}/api/now/table/incident/{incident_id}",
                json=fields,
                headers=self._headers(),
            )
            if resp.status_code != 200:
                logger.error("servicenow_update_failed", status=resp.status_code)
            return {"id": incident_id, **fields}
