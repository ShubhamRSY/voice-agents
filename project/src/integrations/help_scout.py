"""Help Scout adapter for shared inbox and customer conversations."""

import httpx
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class HelpScoutClient:
    def __init__(self, api_key: str | None = None, mailbox_id: str | None = None):
        settings = get_settings()
        self.api_key = api_key or settings.help_scout_api_key
        self.mailbox_id = mailbox_id or settings.help_scout_mailbox_id
        self.base_url = "https://api.helpscout.net/v2"

    def _is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def create_conversation(self, subject: str, body: str, customer_email: str) -> dict:
        if not self._is_configured():
            return {"id": 1, "subject": subject, "status": "active"}

        payload = {
            "subject": subject,
            "customer": {"email": customer_email},
            "mailboxId": int(self.mailbox_id) if self.mailbox_id else None,
            "type": "email",
            "status": "active",
            "threads": [{"type": "customer", "customer": {"email": customer_email}, "text": body}],
        }
        if not self.mailbox_id:
            payload.pop("mailboxId")

        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/conversations", json=payload, headers=self._headers())
            if resp.status_code not in (200, 201):
                logger.error("help_scout_conversation_failed", status=resp.status_code)
                return {"id": None, "subject": subject, "status": "failed"}
            location = resp.headers.get("Resource-URI", "")
            conv_id = location.rstrip("/").split("/")[-1] if location else None
            return {"id": conv_id, "subject": subject, "status": "active"}
