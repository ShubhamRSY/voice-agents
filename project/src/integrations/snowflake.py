"""Snowflake adapter for analytics and conversation data warehouse sync."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class SnowflakeClient:
    def __init__(
        self,
        account: str | None = None,
        user: str | None = None,
        password: str | None = None,
        warehouse: str | None = None,
        database: str | None = None,
        schema: str | None = None,
    ):
        settings = get_settings()
        self.account = account or settings.snowflake_account
        self.user = user or settings.snowflake_user
        self.password = password or settings.snowflake_password
        self.warehouse = warehouse or settings.snowflake_warehouse
        self.database = database or settings.snowflake_database
        self.schema = schema or settings.snowflake_schema or "PUBLIC"
        self.base_url = f"https://{self.account}.snowflakecomputing.com"

    def _is_configured(self) -> bool:
        return bool(self.account and self.user and self.password and self.warehouse and self.database)

    async def _session_token(self) -> str | None:
        account_name = self.account.split(".")[0]
        payload = {
            "data": {
                "ACCOUNT_NAME": account_name,
                "LOGIN_NAME": self.user,
                "PASSWORD": self.password,
            }
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{self.base_url}/session/v1/login-request", json=payload)
            if resp.status_code != 200:
                logger.error("snowflake_login_failed", status=resp.status_code)
                return None
            return resp.json().get("data", {}).get("token")

    async def execute_sql(self, statement: str) -> dict:
        if not self._is_configured():
            return {"status": "mock_ok", "statement": statement[:120]}

        token = await self._session_token()
        if not token:
            return {"status": "failed", "statement": statement, "error": "login_failed"}

        headers = {
            "Authorization": f'Snowflake Token="{token}"',
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "statement": statement,
            "warehouse": self.warehouse,
            "database": self.database,
            "schema": self.schema,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.base_url}/api/v2/statements", json=body, headers=headers)
            if resp.status_code not in (200, 202):
                logger.error("snowflake_sql_failed", status=resp.status_code)
                return {"status": "failed", "statement": statement}
            data = resp.json()
            return {
                "status": "ok",
                "statement_handle": data.get("statementHandle"),
                "message": data.get("message"),
            }

    async def insert_conversation_event(
        self,
        session_id: str,
        channel: str,
        sentiment: str = "",
        summary: str = "",
    ) -> dict:
        safe_summary = summary.replace("'", "''")[:500]
        sql = (
            f"INSERT INTO conversation_events (session_id, channel, sentiment, summary) "
            f"VALUES ('{session_id}', '{channel}', '{sentiment}', '{safe_summary}')"
        )
        return await self.execute_sql(sql)
