"""Azure DevOps adapter for work items and engineering workflows."""

import base64
import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class AzureDevOpsClient:
    def __init__(
        self,
        org: str | None = None,
        project: str | None = None,
        pat: str | None = None,
    ):
        settings = get_settings()
        self.org = org or settings.azure_devops_org
        self.project = project or settings.azure_devops_project
        self.pat = pat or settings.azure_devops_pat
        self.base_url = f"https://dev.azure.com/{self.org}/{self.project}/_apis"

    def _is_configured(self) -> bool:
        return bool(self.org and self.project and self.pat)

    def _headers(self) -> dict:
        token = base64.b64encode(f":{self.pat}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json-patch+json",
        }

    async def create_work_item(self, title: str, description: str = "", work_item_type: str = "Task") -> dict:
        if not self._is_configured():
            return {"id": 1, "title": title, "url": "https://dev.azure.com/mock"}

        payload = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": description},
        ]
        url = f"{self.base_url}/wit/workitems/${work_item_type}?api-version=7.0"

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            if resp.status_code not in (200, 201):
                logger.error("azure_devops_work_item_failed", status=resp.status_code)
                return {"id": None, "title": title}
            data = resp.json()
            return {"id": data.get("id"), "title": data.get("fields", {}).get("System.Title"), "url": data.get("url")}
