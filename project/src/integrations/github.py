"""GitHub adapter for issue tracking and project management."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class GitHubClient:
    def __init__(self, token: str | None = None, repo: str | None = None):
        settings = get_settings()
        self.token = token or settings.github_token
        self.repo = repo or settings.github_repo
        self.base_url = "https://api.github.com"

    def _is_configured(self) -> bool:
        return bool(self.token and self.repo)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v3+json",
        }

    async def create_issue(self, title: str, body: str = "", labels: list[str] | None = None) -> dict:
        if not self._is_configured():
            return {"id": 1, "number": 1, "title": title, "state": "open"}

        payload: dict = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/repos/{self.repo}/issues",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("github_issue_failed", status=resp.status_code)
                return {"id": None, "number": None, "title": title, "state": "failed"}
            data = resp.json()
            return {
                "id": data.get("id"),
                "number": data.get("number"),
                "title": data.get("title"),
                "state": data.get("state"),
                "html_url": data.get("html_url"),
            }

    async def list_issues(self, state: str = "open", per_page: int = 20) -> list[dict]:
        if not self._is_configured():
            return [{"id": 1, "number": 1, "title": "Mock issue", "state": "open"}]

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/repos/{self.repo}/issues",
                params={"state": state, "per_page": per_page},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return []
            return resp.json()

    async def create_issue_comment(self, issue_number: int, body: str) -> dict:
        if not self._is_configured():
            return {"id": 1, "body": body}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/repos/{self.repo}/issues/{issue_number}/comments",
                json={"body": body},
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("github_comment_failed", status=resp.status_code)
                return {"id": None, "body": body}
            return resp.json()
