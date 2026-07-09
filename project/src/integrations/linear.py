"""Linear adapter for issue tracking."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class LinearClient:
    def __init__(self, api_key: str | None = None, team_id: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.linear_api_key
        self.team_id = team_id or settings.linear_team_id
        self.api_url = "https://api.linear.app/graphql"

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": self.api_key, "Content-Type": "application/json"}

    async def create_issue(self, title: str, description: str = "") -> dict:
        if not self._is_configured():
            return {"id": "lin-mock-001", "title": title, "identifier": "NX-1"}

        mutation = """
        mutation ($title: String!, $description: String, $teamId: String!) {
            issueCreate(input: {title: $title, description: $description, teamId: $teamId}) {
                issue { id title identifier url }
            }
        }
        """
        variables = {"title": title, "description": description, "teamId": self.team_id or ""}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.api_url,
                json={"query": mutation, "variables": variables},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                logger.error("linear_issue_failed", status=resp.status_code)
                return {"id": None, "title": title, "identifier": None}
            issue = resp.json().get("data", {}).get("issueCreate", {}).get("issue", {})
            return {
                "id": issue.get("id"),
                "title": issue.get("title"),
                "identifier": issue.get("identifier"),
                "url": issue.get("url"),
            }
