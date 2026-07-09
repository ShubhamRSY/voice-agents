"""Monday.com adapter for project and workflow management."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class MondayClient:
    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.monday_api_key
        self.api_url = "https://api.monday.com/v2"

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": self.api_key, "Content-Type": "application/json"}

    async def create_item(self, board_id: int, name: str, column_values: dict | None = None) -> dict:
        if not self._is_configured():
            return {"id": "item-mock-001", "name": name}

        cols = column_values or {}
        query = """
        mutation ($board_id: Int!, $name: String!, $column_values: JSON) {
            create_item (board_id: $board_id, item_name: $name, column_values: $column_values) {
                id name
            }
        }
        """
        variables = {"board_id": board_id, "name": name, "column_values": cols}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.api_url,
                json={"query": query, "variables": variables},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                logger.error("monday_create_item_failed", status=resp.status_code)
                return {"id": None, "name": name}
            data = resp.json().get("data", {}).get("create_item", {})
            return {"id": data.get("id"), "name": data.get("name")}
