"""BambooHR adapter for employee and HRIS context."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class BambooHRClient:
    def __init__(self, subdomain: str | None = None, api_key: str | None = None):
        settings = get_settings()
        self.subdomain = subdomain or settings.bamboohr_subdomain
        self.api_key = api_key or settings.bamboohr_api_key
        self.base_url = f"https://api.bamboohr.com/api/gateway.php/{self.subdomain}/v1"

    def _is_configured(self) -> bool:
        return bool(self.subdomain and self.api_key)

    def _auth(self) -> tuple[str, str]:
        return (self.api_key, "x")

    async def find_employee(self, email: str) -> dict | None:
        if not self._is_configured():
            return {"id": 1, "workEmail": email, "displayName": "Mock Employee"}

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/employees/directory",
                auth=self._auth(),
            )
            if resp.status_code != 200:
                return None
            for emp in resp.json().get("employees", []):
                if emp.get("workEmail", "").lower() == email.lower():
                    return emp
            return None
