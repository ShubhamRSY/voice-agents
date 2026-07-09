"""Microsoft SharePoint adapter for document and list item sync."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class SharePointClient:
    def __init__(self, site_url: str | None = None, access_token: str | None = None, list_name: str | None = None):
        settings = get_settings()
        self.site_url = (site_url or settings.sharepoint_site_url).rstrip("/")
        self.access_token = access_token or settings.sharepoint_access_token
        self.list_name = list_name or settings.sharepoint_list_name or "NexusEvents"

    def _is_configured(self) -> bool:
        return bool(self.site_url and self.access_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "Accept": "application/json"}

    async def add_list_item(self, title: str, fields: dict | None = None) -> dict:
        if not self._is_configured():
            return {"id": 1, "title": title}
        payload = {"fields": {"Title": title, **(fields or {})}}
        url = f"{self.site_url}/_api/web/lists/getbytitle('{self.list_name}')/items"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            if resp.status_code not in (200, 201):
                logger.error("sharepoint_item_failed", status=resp.status_code)
                return {"id": None, "title": title}
            data = resp.json()
            return {"id": data.get("Id") or data.get("id"), "title": title}
