"""Salesforce CRM adapter for contact lookup, case creation, and record updates."""

from typing import Any

import httpx
import structlog

from src.config import get_settings
from src.integrations.crm import CRMClient, _mock_customer

logger = structlog.get_logger()


class SalesforceClient(CRMClient):
    BASE_URL = "https://your_instance.salesforce.com"
    AUTH_URL = "https://login.salesforce.com/services/oauth2/token"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        settings = get_settings()
        self.client_id = client_id or settings.salesforce_client_id
        self.client_secret = client_secret or settings.salesforce_client_secret
        self._access_token: str | None = None
        self._instance_url: str | None = None

    def _is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _authenticate(self) -> None:
        if not self._is_configured():
            return
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            if resp.status_code != 200:
                logger.error("salesforce_auth_failed", status=resp.status_code)
                return
            data = resp.json()
            self._access_token = data.get("access_token")
            self._instance_url = data.get("instance_url")

    def _headers(self) -> dict:
        if not self._access_token:
            return {}
        return {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

    async def lookup_customer(self, identifier: str) -> dict[str, Any] | None:
        if not self._is_configured():
            return _mock_customer(identifier)

        if not self._access_token:
            await self._authenticate()
        if not self._access_token:
            return _mock_customer(identifier)

        is_email = "@" in identifier
        fields = "Id,Email,FirstName,LastName,Phone"
        if is_email:
            query = f"SELECT {fields} FROM Contact WHERE Email = '{identifier}' LIMIT 1"
        else:
            query = f"SELECT {fields} FROM Contact WHERE Phone = '{identifier}' LIMIT 1"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._instance_url}/services/data/v58.0/query",
                headers=self._headers(),
                params={"q": query},
            )
            if resp.status_code != 200:
                logger.warning("salesforce_query_failed", status=resp.status_code)
                return None
            data = resp.json()
            records = data.get("records", [])
            if not records:
                return None
            r = records[0]
            return {
                "id": r["Id"],
                "email": r.get("Email", ""),
                "name": f"{r.get('FirstName', '')} {r.get('LastName', '')}".strip(),
                "phone": r.get("Phone", ""),
            }

    async def create_ticket(self, subject: str, description: str, customer_id: str) -> dict:
        if not self._is_configured():
            return {"id": "sf-mock-case-001", "subject": subject, "status": "New"}

        if not self._access_token:
            await self._authenticate()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._instance_url}/services/data/v58.0/sobjects/Case",
                headers=self._headers(),
                json={
                    "Subject": subject,
                    "Description": description,
                    "ContactId": customer_id,
                    "Origin": "AI Agent",
                    "Status": "New",
                },
            )
            if resp.status_code not in (200, 201):
                logger.error("salesforce_ticket_failed", status=resp.status_code)
                return {"id": "error", "subject": subject, "status": "failed"}
            data = resp.json()
            return {"id": data.get("id", ""), "subject": subject, "status": "New"}

    async def update_record(self, customer_id: str, fields: dict[str, Any]) -> dict:
        if not self._is_configured():
            return {"id": customer_id, **fields}

        if not self._access_token:
            await self._authenticate()

        mapped = {}
        if "firstname" in fields:
            mapped["FirstName"] = fields["firstname"]
        if "lastname" in fields:
            mapped["LastName"] = fields["lastname"]
        if "email" in fields:
            mapped["Email"] = fields["email"]
        if "phone" in fields:
            mapped["Phone"] = fields["phone"]

        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{self._instance_url}/services/data/v58.0/sobjects/Contact/{customer_id}",
                headers=self._headers(),
                json=mapped,
            )
            if resp.status_code not in (200, 204):
                logger.error("salesforce_update_failed", status=resp.status_code)
            return {"id": customer_id, **fields}
