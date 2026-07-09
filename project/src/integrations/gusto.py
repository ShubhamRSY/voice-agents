"""Gusto HRIS adapter for employee and payroll context."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class GustoClient:
    def __init__(self, access_token: str | None = None, company_id: str | None = None):
        settings = get_settings()
        self.access_token = access_token or settings.gusto_access_token
        self.company_id = company_id or settings.gusto_company_id
        self.base_url = "https://api.gusto.com/v1"

    def _is_configured(self) -> bool:
        return bool(self.access_token and self.company_id)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def list_employees(self) -> list[dict]:
        if not self._is_configured():
            return [{"id": 1, "email": "mock@gusto.com", "first_name": "Mock"}]
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/companies/{self.company_id}/employees", headers=self._headers())
            if resp.status_code != 200:
                logger.error("gusto_employees_failed", status=resp.status_code)
                return []
            return resp.json()

    async def find_employee(self, email: str) -> dict | None:
        for emp in await self.list_employees():
            if emp.get("email", "").lower() == email.lower():
                return emp
        return None
