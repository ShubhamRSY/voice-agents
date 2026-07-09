"""Zoho CRM adapter for leads and contact management."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class ZohoCRMClient:
    def __init__(self, access_token: str | None = None, api_domain: str | None = None):
        settings = get_settings()
        self.access_token = access_token or settings.zoho_access_token
        self.api_domain = api_domain or settings.zoho_api_domain or "www.zohoapis.com"
        self.base_url = f"https://{self.api_domain}/crm/v2"

    def _is_configured(self) -> bool:
        return bool(self.access_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Zoho-oauthtoken {self.access_token}", "Content-Type": "application/json"}

    async def create_lead(self, last_name: str, email: str = "", company: str = "") -> dict:
        if not self._is_configured():
            return {"id": "zoho-mock-001", "Last_Name": last_name, "status": "created"}

        record: dict = {"Last_Name": last_name}
        if email:
            record["Email"] = email
        if company:
            record["Company"] = company

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/Leads",
                json={"data": [record]},
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("zoho_lead_failed", status=resp.status_code)
                return {"id": None, "Last_Name": last_name, "status": "failed"}
            results = resp.json().get("data", [])
            detail = results[0].get("details", {}) if results else {}
            return {"id": detail.get("id"), "Last_Name": last_name, "status": "created"}
