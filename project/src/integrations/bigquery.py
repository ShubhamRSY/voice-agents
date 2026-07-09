"""Google BigQuery adapter for analytics and conversation data sync."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class BigQueryClient:
    def __init__(
        self,
        project_id: str | None = None,
        dataset_id: str | None = None,
        table_id: str | None = None,
        access_token: str | None = None,
    ):
        settings = get_settings()
        self.project_id = project_id or settings.bigquery_project_id
        self.dataset_id = dataset_id or settings.bigquery_dataset_id
        self.table_id = table_id or settings.bigquery_table_id
        self.access_token = access_token or settings.bigquery_access_token

    def _is_configured(self) -> bool:
        return bool(self.project_id and self.dataset_id and self.table_id and self.access_token)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def insert_row(self, row: dict) -> dict:
        if not self._is_configured():
            return {"status": "mock_ok", "row": row}

        url = (
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{self.project_id}"
            f"/datasets/{self.dataset_id}/tables/{self.table_id}/insertAll"
        )
        payload = {"rows": [{"json": row}]}

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            if resp.status_code != 200:
                logger.error("bigquery_insert_failed", status=resp.status_code)
                return {"status": "failed", "row": row}
            data = resp.json()
            errors = data.get("insertErrors", [])
            if errors:
                return {"status": "failed", "errors": errors}
            return {"status": "ok", "row": row}

    async def insert_conversation_event(
        self,
        session_id: str,
        channel: str,
        sentiment: str = "",
        summary: str = "",
    ) -> dict:
        return await self.insert_row({
            "session_id": session_id,
            "channel": channel,
            "sentiment": sentiment,
            "summary": summary[:500],
        })
