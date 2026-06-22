"""CRM integration layer with HubSpot and Salesforce adapters."""

from abc import ABC, abstractmethod
from typing import Any

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class CRMClient(ABC):
    @abstractmethod
    async def lookup_customer(self, identifier: str) -> dict[str, Any] | None:
        pass

    @abstractmethod
    async def create_ticket(self, subject: str, description: str, customer_id: str) -> dict:
        pass

    @abstractmethod
    async def update_record(self, customer_id: str, fields: dict[str, Any]) -> dict:
        pass


class HubSpotClient(CRMClient):
    BASE_URL = "https://api.hubapi.com"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_settings().hubspot_api_key

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def lookup_customer(self, identifier: str) -> dict[str, Any] | None:
        if not self.api_key:
            return _mock_customer(identifier)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/crm/v3/objects/contacts/{identifier}",
                headers=self._headers(),
                params={"properties": "email,firstname,lastname,phone"},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return {
                "id": data["id"],
                "email": data["properties"].get("email"),
                "name": f"{data['properties'].get('firstname', '')} {data['properties'].get('lastname', '')}".strip(),
                "phone": data["properties"].get("phone"),
            }

    async def create_ticket(self, subject: str, description: str, customer_id: str) -> dict:
        if not self.api_key:
            return {"id": "mock-ticket-001", "subject": subject, "status": "open"}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/crm/v3/objects/tickets",
                headers=self._headers(),
                json={
                    "properties": {
                        "subject": subject,
                        "content": description,
                        "hs_pipeline_stage": "1",
                    },
                    "associations": [
                        {
                            "to": {"id": customer_id},
                            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 16}],
                        }
                    ],
                },
            )
            response.raise_for_status()
            return response.json()

    async def update_record(self, customer_id: str, fields: dict[str, Any]) -> dict:
        if not self.api_key:
            return {"id": customer_id, **fields}

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.BASE_URL}/crm/v3/objects/contacts/{customer_id}",
                headers=self._headers(),
                json={"properties": fields},
            )
            response.raise_for_status()
            return response.json()


def _mock_customer(identifier: str) -> dict[str, Any]:
    return {
        "id": "cust-001",
        "email": f"{identifier}@example.com" if "@" not in identifier else identifier,
        "name": "Jane Doe",
        "phone": "+15551234567" if "@" in identifier else identifier,
        "tier": "premium",
        "account_status": "active",
    }


def get_crm_client() -> CRMClient:
    settings = get_settings()
    provider = settings.crm_provider or "hubspot"
    if provider == "salesforce":
        from src.integrations.salesforce import SalesforceClient
        return SalesforceClient()
    return HubSpotClient()
