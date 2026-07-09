"""ADP Workforce Now adapter for employee context."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class ADPClient:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        settings = get_settings()
        self.client_id = client_id or settings.adp_client_id
        self.client_secret = client_secret or settings.adp_client_secret
        self.base_url = "https://api.adp.com"

    def _is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def find_worker(self, email: str) -> dict | None:
        if not self._is_configured():
            return {"id": "adp-mock-001", "email": email, "name": "Mock Employee"}
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(f"{self.base_url}/auth/oauth/v2/token", data={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret})
            if token_resp.status_code != 200:
                return None
            token = token_resp.json().get("access_token")
            resp = await client.get(f"{self.base_url}/hr/v2/workers", headers={"Authorization": f"Bearer {token}"}, params={"$filter": f"workers/workAssignments/assignedWorkLocations/name eq '{email}'"})
            if resp.status_code != 200:
                return {"id": "lookup", "email": email}
            return resp.json().get("workers", [{}])[0] if resp.json().get("workers") else {"id": "lookup", "email": email}
