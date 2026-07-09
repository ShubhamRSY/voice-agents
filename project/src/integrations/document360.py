"""Document360 adapter for knowledge base articles."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class Document360Client:
    def __init__(self, api_token: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.api_token = api_token or settings.document360_api_token
        self.base_url = (base_url or settings.document360_base_url).rstrip("/")

    def _is_configured(self) -> bool:
        return bool(self.api_token and self.base_url)

    def _headers(self) -> dict:
        return {"api_token": self.api_token, "Content-Type": "application/json"}

    async def create_article(self, title: str, content: str = "", category_id: str = "") -> dict:
        if not self._is_configured():
            return {"id": "d360-mock-001", "title": title}
        payload = {"title": title, "content": content or title, "category_id": category_id or None}
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/v2/Articles", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201):
                logger.error("document360_article_failed", status=resp.status_code)
                return {"id": None, "title": title}
            data = resp.json().get("data", resp.json())
            return {"id": data.get("id"), "title": data.get("title", title)}
