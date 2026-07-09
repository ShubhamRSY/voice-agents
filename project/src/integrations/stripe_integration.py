"""Stripe adapter for billing events and customer lookup."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class StripeClient:
    def __init__(self, secret_key: str | None = None):
        settings = get_settings()
        self.secret_key = secret_key or settings.stripe_secret_key
        self.base_url = "https://api.stripe.com/v1"

    def _is_configured(self) -> bool:
        return bool(self.secret_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.secret_key}"}

    async def find_customer(self, email: str) -> dict | None:
        if not self._is_configured():
            return {"id": "cus_mock_001", "email": email}

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/customers",
                params={"email": email, "limit": 1},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return None
            data = resp.json().get("data", [])
            return data[0] if data else None

    async def create_customer(self, email: str, name: str = "") -> dict:
        if not self._is_configured():
            return {"id": "cus_mock_001", "email": email}

        payload = {"email": email}
        if name:
            payload["name"] = name

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/customers",
                data=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("stripe_customer_failed", status=resp.status_code)
                return {"id": None, "email": email}
            return resp.json()
