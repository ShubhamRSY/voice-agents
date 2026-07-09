"""Asana adapter for project and task management."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class AsanaClient:
    def __init__(self, access_token: str | None = None):
        settings = get_settings()
        self.access_token = access_token or settings.asana_access_token
        self.base_url = "https://app.asana.com/api/1.0"

    def _is_configured(self) -> bool:
        return bool(self.access_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def create_task(self, name: str, notes: str = "", project_gid: str = "", assignee: str = "") -> dict:
        if not self._is_configured():
            return {"gid": "task-mock-001", "name": name, "resource_type": "task"}

        data = {"name": name, "notes": notes}
        if project_gid:
            data["projects"] = [project_gid]
        if assignee:
            data["assignee"] = assignee

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/tasks",
                json={"data": data},
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("asana_task_failed", status=resp.status_code)
                return {"gid": None, "name": name, "resource_type": "error"}
            data = resp.json().get("data", {})
            return {"gid": data.get("gid"), "name": data.get("name"), "resource_type": "task"}

    async def find_project(self, name: str) -> dict | None:
        if not self._is_configured():
            return {"gid": "project-mock-001", "name": name}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/projects",
                params={"search": name},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return None
            projects = resp.json().get("data", [])
            return projects[0] if projects else None
