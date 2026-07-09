"""Mailchimp adapter for marketing lists and audience sync."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class MailchimpClient:
    def __init__(self, api_key: str | None = None, list_id: str | None = None, server: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.mailchimp_api_key
        self.list_id = list_id or settings.mailchimp_list_id
        self.server = server or settings.mailchimp_server or (self.api_key.split("-")[-1] if self.api_key and "-" in self.api_key else "")
        self.base_url = f"https://{self.server}.api.mailchimp.com/3.0" if self.server else ""

    def _is_configured(self) -> bool:
        return bool(self.api_key and self.server)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def add_subscriber(self, email: str, first_name: str = "", last_name: str = "") -> dict:
        if not self._is_configured():
            return {"id": "mc-mock-001", "email": email, "status": "subscribed"}
        if not self.list_id:
            return {"id": None, "email": email, "status": "failed", "error": "list_id_required"}

        payload = {
            "email_address": email,
            "status": "subscribed",
            "merge_fields": {"FNAME": first_name, "LNAME": last_name},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/lists/{self.list_id}/members",
                json=payload,
                headers=self._headers(),
            )
            if resp.status_code not in (200, 201):
                logger.error("mailchimp_subscriber_failed", status=resp.status_code)
                return {"id": None, "email": email, "status": "failed"}
            data = resp.json()
            return {"id": data.get("id"), "email": data.get("email_address"), "status": data.get("status")}
