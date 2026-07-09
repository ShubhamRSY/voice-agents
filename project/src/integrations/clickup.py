"""ClickUp adapter for task and project management."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class ClickUpClient:
    def __init__(self, api_token: str | None = None, list_id: str | None = None):
        settings = get_settings()
        self.api_token = api_token or settings.clickup_api_token
        self.list_id = list_id or settings.clickup_list_id
        self.base_url = "https://api.clickup.com/api/v2"

    def _is_configured(self) -> bool:
        return bool(self.api_token)

    def _headers(self) -> dict:
        return {"Authorization": self.api_token, "Content-Type": "application/json"}

    async def create_task(self, name: str, description: str = "", list_id: str = "") -> dict:
        if not self._is_configured():
            return {"id": "cu-mock-001", "name": name, "status": "open"}

        target_list = list_id or self.list_id
        if not target_list:
            return {"id": None, "name": name, "status": "failed", "error": "list_id_required"}

        payload = {"name": name, "description": description}
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/list/{target_list}/task",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("clickup_task_failed", status=resp.status_code)
                return {"id": None, "name": name, "status": "failed"}
            data = resp.json()
            return {"id": data.get("id"), "name": data.get("name"), "status": data.get("status", {}).get("status")}
