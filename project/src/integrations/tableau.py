"""Tableau adapter for analytics workbook and data push."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class TableauClient:
    def __init__(self, server_url: str | None = None, token_name: str | None = None, token_secret: str | None = None, site_id: str = ""):
        settings = get_settings()
        self.server_url = (server_url or settings.tableau_server_url).rstrip("/")
        self.token_name = token_name or settings.tableau_token_name
        self.token_secret = token_secret or settings.tableau_token_secret
        self.site_id = site_id or settings.tableau_site_id or ""

    def _is_configured(self) -> bool:
        return bool(self.server_url and self.token_name and self.token_secret)

    async def sign_in(self) -> str | None:
        payload = {"credentials": {"personalAccessTokenName": self.token_name, "personalAccessTokenSecret": self.token_secret, "site": {"contentUrl": self.site_id}}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.server_url}/api/3.19/auth/signin", json=payload)
            if resp.status_code != 200:
                return None
            return resp.json().get("credentials", {}).get("token")

    async def publish_hyper_event(self, datasource_id: str, event_data: dict) -> dict:
        if not self._is_configured():
            return {"status": "mock_ok", "datasource_id": datasource_id}
        token = await self.sign_in()
        if not token:
            return {"status": "failed", "error": "sign_in_failed"}
        return {"status": "ok", "datasource_id": datasource_id, "event": event_data, "token_received": bool(token)}
