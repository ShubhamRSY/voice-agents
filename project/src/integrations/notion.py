"""Notion adapter for knowledge management and documentation."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class NotionClient:
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.notion_api_key
        self.base_url = "https://api.notion.com/v1"
        self.version = "2022-06-28"

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": self.version,
        }

    async def create_page(self, parent_page_id: str, title: str, content: str = "") -> dict:
        if not self._is_configured():
            return {"id": "page-mock-001", "title": title, "url": "https://notion.so/mock"}

        children = []
        if content:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]},
            })

        payload = {
            "parent": {"page_id": parent_page_id},
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": title}}]},
            },
        }
        if children:
            payload["children"] = children

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/pages",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("notion_page_failed", status=resp.status_code)
                return {"id": None, "title": title}
            data = resp.json()
            return {"id": data.get("id"), "title": title, "url": data.get("url")}

    async def search(self, query: str) -> list[dict]:
        if not self._is_configured():
            return [{"id": "mock-001", "title": query}]
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/search",
                json={"query": query},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                logger.error("notion_search_failed", status=resp.status_code)
                return []
            return resp.json().get("results", [])
