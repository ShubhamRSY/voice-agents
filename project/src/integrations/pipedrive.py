"""Pipedrive adapter for CRM deals and contact lookup."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class PipedriveClient:
    def __init__(self, api_token: str | None = None, domain: str | None = None):
        settings = get_settings()
        self.api_token = api_token or settings.pipedrive_api_token
        self.domain = domain or settings.pipedrive_domain or "api"
        self.base_url = f"https://{self.domain}.pipedrive.com/api/v1"

    def _is_configured(self) -> bool:
        return bool(self.api_token)

    def _params(self, extra: dict | None = None) -> dict:
        params = {"api_token": self.api_token}
        if extra:
            params.update(extra)
        return params

    async def create_deal(self, title: str, person_id: int | None = None, value: float = 0) -> dict:
        if not self._is_configured():
            return {"id": 1, "title": title, "status": "open"}

        payload: dict = {"title": title}
        if person_id:
            payload["person_id"] = person_id
        if value:
            payload["value"] = value

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/deals",
                params=self._params(),
                json=payload,
            )
            if resp.status_code not in (200, 201):
                logger.error("pipedrive_deal_failed", status=resp.status_code)
                return {"id": None, "title": title, "status": "failed"}
            data = resp.json().get("data", {})
            return {"id": data.get("id"), "title": data.get("title"), "status": data.get("status")}

    async def find_person(self, email: str) -> dict | None:
        if not self._is_configured():
            return {"id": 1, "email": email, "name": "Mock Contact"}

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/persons/search",
                params=self._params({"term": email, "fields": "email", "exact_match": True}),
            )
            if resp.status_code != 200:
                return None
            items = resp.json().get("data", {}).get("items", [])
            return items[0]["item"] if items else None
