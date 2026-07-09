"""Shopify adapter for ecommerce order and customer context."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class ShopifyClient:
    def __init__(self, shop_domain: str | None = None, access_token: str | None = None):
        settings = get_settings()
        self.shop_domain = shop_domain or settings.shopify_shop_domain
        self.access_token = access_token or settings.shopify_access_token
        self.base_url = f"https://{self.shop_domain}/admin/api/2024-01"

    def _is_configured(self) -> bool:
        return bool(self.shop_domain and self.access_token)

    def _headers(self) -> dict:
        return {"X-Shopify-Access-Token": self.access_token, "Content-Type": "application/json"}

    async def find_customer(self, email: str) -> dict | None:
        if not self._is_configured():
            return {"id": 1, "email": email, "first_name": "Mock"}

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/customers/search.json",
                params={"query": f"email:{email}"},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return None
            customers = resp.json().get("customers", [])
            return customers[0] if customers else None

    async def get_order(self, order_id: int) -> dict | None:
        if not self._is_configured():
            return {"id": order_id, "name": "#1001", "financial_status": "paid"}

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/orders/{order_id}.json",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return None
            return resp.json().get("order")
