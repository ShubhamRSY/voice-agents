"""Adobe Marketo adapter for lead capture and marketing automation."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class MarketoClient:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.client_id = client_id or settings.marketo_client_id
        self.client_secret = client_secret or settings.marketo_client_secret
        self.base_url = (base_url or settings.marketo_base_url).rstrip("/")

    def _is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.base_url)

    async def _token(self) -> str | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/identity/oauth/token", params={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret})
            if resp.status_code != 200:
                return None
            return resp.json().get("access_token")

    async def create_lead(self, email: str, first_name: str = "", last_name: str = "") -> dict:
        if not self._is_configured():
            return {"id": 1, "email": email, "status": "created"}
        token = await self._token()
        if not token:
            return {"id": None, "email": email, "status": "failed"}
        payload = {"action": "createOnly", "input": [{"email": email, "firstName": first_name, "lastName": last_name}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/rest/v1/leads.json", json=payload, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code != 200:
                logger.error("marketo_lead_failed", status=resp.status_code)
                return {"id": None, "email": email, "status": "failed"}
            result = resp.json().get("result", [{}])[0]
            return {"id": result.get("id"), "email": email, "status": result.get("status")}
