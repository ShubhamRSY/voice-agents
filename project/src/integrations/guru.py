"""Guru adapter for knowledge cards and search."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class GuruClient:
    def __init__(self, api_token: str | None = None, collection_id: str | None = None):
        settings = get_settings()
        self.api_token = api_token or settings.guru_api_token
        self.collection_id = collection_id or settings.guru_collection_id
        self.base_url = "https://api.getguru.com/api/v1"

    def _is_configured(self) -> bool:
        return bool(self.api_token)

    def _auth(self) -> tuple[str, str]:
        return (self.api_token, "")

    async def create_card(self, title: str, content: str = "") -> dict:
        if not self._is_configured():
            return {"id": "guru-mock-001", "title": title}
        payload = {"preferredPhrase": title, "content": content or title}
        if self.collection_id:
            payload["collection"] = {"id": self.collection_id}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/cards", json=payload, auth=self._auth())
            if resp.status_code not in (200, 201):
                logger.error("guru_card_failed", status=resp.status_code)
                return {"id": None, "title": title}
            data = resp.json()
            return {"id": data.get("id"), "title": data.get("preferredPhrase")}
