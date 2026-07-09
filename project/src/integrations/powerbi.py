"""Microsoft Power BI adapter for dataset row push."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class PowerBIClient:
    def __init__(self, access_token: str | None = None, workspace_id: str | None = None, dataset_id: str | None = None):
        settings = get_settings()
        self.access_token = access_token or settings.powerbi_access_token
        self.workspace_id = workspace_id or settings.powerbi_workspace_id
        self.dataset_id = dataset_id or settings.powerbi_dataset_id

    def _is_configured(self) -> bool:
        return bool(self.access_token and self.dataset_id)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def push_row(self, table_name: str, row: dict) -> dict:
        if not self._is_configured():
            return {"status": "mock_ok", "table": table_name, "row": row}
        ws = self.workspace_id or "me"
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{self.dataset_id}/tables/{table_name}/rows"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"rows": [row]}, headers=self._headers())
            if resp.status_code not in (200, 201, 202):
                logger.error("powerbi_push_failed", status=resp.status_code)
                return {"status": "failed", "table": table_name}
            return {"status": "ok", "table": table_name}
