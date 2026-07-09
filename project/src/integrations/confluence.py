"""Atlassian Confluence adapter for knowledge base pages."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class ConfluenceClient:
    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        space_key: str | None = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.confluence_base_url).rstrip("/")
        self.email = email or settings.confluence_user_email
        self.api_token = api_token or settings.confluence_api_token
        self.space_key = space_key or settings.confluence_space_key or "NX"

    def _is_configured(self) -> bool:
        return bool(self.base_url and self.email and self.api_token)

    def _auth(self) -> tuple[str, str]:
        return (self.email, self.api_token)

    async def create_page(self, title: str, body: str = "") -> dict:
        if not self._is_configured():
            return {"id": "conf-mock-001", "title": title, "url": "https://confluence.mock/pages/1"}

        payload = {
            "type": "page",
            "title": title,
            "space": {"key": self.space_key},
            "body": {"storage": {"value": body or title, "representation": "storage"}},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/wiki/rest/api/content",
                json=payload,
                auth=self._auth(),
            )
            if resp.status_code not in (200, 201):
                logger.error("confluence_page_failed", status=resp.status_code)
                return {"id": None, "title": title}
            data = resp.json()
            links = data.get("_links", {})
            return {"id": data.get("id"), "title": data.get("title"), "url": links.get("base", "") + links.get("webui", "")}
