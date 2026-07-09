"""Workday adapter for HRIS worker lookup."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class WorkdayClient:
    def __init__(self, tenant: str | None = None, username: str | None = None, password: str | None = None):
        settings = get_settings()
        self.tenant = tenant or settings.workday_tenant
        self.username = username or settings.workday_username
        self.password = password or settings.workday_password
        self.base_url = f"https://wd2-impl-services1.workday.com/ccx/service/{self.tenant}/Human_Resources/v40.0" if self.tenant else ""

    def _is_configured(self) -> bool:
        return bool(self.tenant and self.username and self.password)

    def _auth(self) -> tuple[str, str]:
        return (self.username, self.password)

    async def find_worker(self, email: str) -> dict | None:
        if not self._is_configured():
            return {"id": "wd-mock-001", "email": email, "name": "Mock Worker"}
        # Simplified REST lookup — production uses Workday RaaS or SOAP
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/workers", params={"email": email}, auth=self._auth())
            if resp.status_code != 200:
                return None
            workers = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else []
            if isinstance(workers, list) and workers:
                return workers[0]
            return {"id": "lookup", "email": email}
