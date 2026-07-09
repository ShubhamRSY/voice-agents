"""Trello adapter for kanban boards and cards."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class TrelloClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_token: str | None = None,
        list_id: str | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.trello_api_key
        self.api_token = api_token or settings.trello_api_token
        self.list_id = list_id or settings.trello_list_id
        self.base_url = "https://api.trello.com/1"

    def _is_configured(self) -> bool:
        return bool(self.api_key and self.api_token)

    def _params(self, extra: dict | None = None) -> dict:
        params = {"key": self.api_key, "token": self.api_token}
        if extra:
            params.update(extra)
        return params

    async def create_card(self, name: str, desc: str = "", list_id: str = "") -> dict:
        if not self._is_configured():
            return {"id": "trello-mock-001", "name": name, "url": "https://trello.com/c/mock"}

        target_list = list_id or self.list_id
        if not target_list:
            return {"id": None, "name": name, "error": "list_id_required"}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/cards",
                params=self._params({"idList": target_list, "name": name, "desc": desc}),
            )
            if resp.status_code not in (200, 201):
                logger.error("trello_card_failed", status=resp.status_code)
                return {"id": None, "name": name}
            data = resp.json()
            return {"id": data.get("id"), "name": data.get("name"), "url": data.get("url")}
