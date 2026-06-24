"""Zendesk adapter for ticket CRUD and contact search."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class ZendeskClient:
    def __init__(self, subdomain: str | None = None, api_key: str | None = None):
        settings = get_settings()
        self.subdomain = subdomain or settings.zendesk_subdomain
        self.api_key = api_key or settings.zendesk_api_key
        self.base_url = f"https://{self.subdomain}.zendesk.com"

    def _is_configured(self) -> bool:
        return bool(self.subdomain and self.api_key)

    def _auth(self) -> tuple[str, str]:
        return f"{self.api_key}/token", ""

    async def create_ticket(self, subject: str, description: str, requester_email: str = "") -> dict:
        if not self._is_configured():
            return {"id": "zd-mock-001", "subject": subject, "status": "new"}

        payload = {"ticket": {"subject": subject, "comment": {"body": description}}}
        if requester_email:
            payload["ticket"]["requester"] = {"email": requester_email}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/v2/tickets.json",
                json=payload,
                auth=self._auth(),
            )
            if resp.status_code not in (200, 201):
                logger.error("zendesk_ticket_failed", status=resp.status_code)
                return {"id": "error", "subject": subject, "status": "failed"}
            data = resp.json()
            return {
                "id": str(data.get("ticket", {}).get("id", "")),
                "subject": subject,
                "status": data.get("ticket", {}).get("status", "new"),
            }

    async def search_contacts(self, query: str) -> list[dict]:
        if not self._is_configured():
            return [{"id": "mock-001", "email": f"{query}@example.com", "name": "Mock User"}]

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v2/users/search.json",
                params={"query": query},
                auth=self._auth(),
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            return [
                {"id": str(u["id"]), "email": u.get("email", ""), "name": u.get("name", "")}
                for u in data.get("users", [])
            ]

    async def update_ticket(self, ticket_id: str, fields: dict) -> dict:
        if not self._is_configured():
            return {"id": ticket_id, **fields}

        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{self.base_url}/api/v2/tickets/{ticket_id}.json",
                json={"ticket": fields},
                auth=self._auth(),
            )
            if resp.status_code != 200:
                logger.error("zendesk_update_failed", status=resp.status_code)
            return {"id": ticket_id, **fields}
