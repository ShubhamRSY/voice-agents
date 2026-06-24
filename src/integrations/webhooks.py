"""Webhook and iPaaS-style integration handlers (n8n/Zapier compatible)."""

import hashlib
import hmac
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class WebhookDispatcher:
    """Dispatch events to external systems via webhooks (n8n, Zapier, custom)."""

    def __init__(self, secret: str = ""):
        self.secret = secret

    def sign_payload(self, payload: bytes) -> str:
        if not self.secret:
            return ""
        return hmac.new(self.secret.encode(), payload, hashlib.sha256).hexdigest()

    async def dispatch(
        self,
        url: str,
        event_type: str,
        data: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict:
        payload = {"event": event_type, "data": data}
        request_headers = {"Content-Type": "application/json", **(headers or {})}

        import json
        body = json.dumps(payload).encode()
        signature = self.sign_payload(body)
        if signature:
            request_headers["X-Webhook-Signature"] = signature

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, content=body, headers=request_headers)
        except Exception as exc:
            logger.warning("webhook_dispatch_failed", url=url, event_type=event_type, error=str(exc))
            return {"status": "failed", "event": event_type, "error": str(exc)}

        if response.status_code >= 400:
            logger.warning("webhook_rejected", url=url, status=response.status_code)
            return {"status": "failed", "event": event_type, "status_code": response.status_code}

        logger.info("webhook_dispatched", event_type=event_type, url=url)
        return {"status": "delivered", "event": event_type}


class IntegrationRouter:
    """Route agent events to configured integrations."""

    def __init__(self):
        self.webhooks: dict[str, str] = {}
        self.dispatcher = WebhookDispatcher()
        self.load_from_vault()

    def load_from_vault(self) -> None:
        from src.config import get_settings
        from src.integrations.secrets_vault import get_secrets_vault

        settings = get_settings()
        self.webhooks = get_secrets_vault().get_webhooks()
        self.dispatcher = WebhookDispatcher(secret=settings.webhook_signing_secret)

    def register_webhook(self, event_type: str, url: str, *, persist: bool = True) -> None:
        self.webhooks[event_type] = url
        if persist:
            from src.integrations.secrets_vault import get_secrets_vault

            get_secrets_vault().set_webhook(event_type, url)

    def unregister_webhook(self, event_type: str, *, persist: bool = True) -> None:
        self.webhooks.pop(event_type, None)
        if persist:
            from src.integrations.secrets_vault import get_secrets_vault

            get_secrets_vault().clear_webhook(event_type)

    async def on_conversation_start(self, session_id: str, channel: str, metadata: dict) -> None:
        await self._emit("conversation.started", {
            "session_id": session_id,
            "channel": channel,
            **metadata,
        })

    async def on_conversation_end(self, session_id: str, outcome: str, metrics: dict) -> None:
        await self._emit("conversation.ended", {
            "session_id": session_id,
            "outcome": outcome,
            **metrics,
        })

    async def on_ticket_created(self, ticket: dict) -> None:
        await self._emit("ticket.created", ticket)

    async def on_escalation(self, session_id: str, reason: str) -> None:
        await self._emit("conversation.escalated", {
            "session_id": session_id,
            "reason": reason,
        })

    async def on_feedback_suggestion(self, agent_id: str, suggestion: dict) -> None:
        await self._emit("feedback.suggestion", {
            "agent_id": agent_id,
            **suggestion,
        })

    async def on_feedback_auto_adjust(self, agent_id: str, adjustments: dict) -> None:
        await self._emit("feedback.auto_adjust", {
            "agent_id": agent_id,
            "adjustments": adjustments,
        })

    async def on_connect_contact_ended(self, contact_id: str, status: str, metrics: dict | None = None) -> None:
        await self._emit("connect.contact_ended", {
            "contact_id": contact_id,
            "status": status,
            **(metrics or {}),
        })

    async def _emit(self, event_type: str, data: dict) -> None:
        url = self.webhooks.get(event_type)
        if url:
            await self.dispatcher.dispatch(url, event_type, data)
