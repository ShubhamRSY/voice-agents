"""Webhook and iPaaS-style integration handlers (n8n/Zapier compatible)."""

import hashlib
import hmac
from typing import Any

import httpx
import structlog
from fastapi import HTTPException

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

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, content=body, headers=request_headers)

        if response.status_code >= 400:
            logger.error("webhook_failed", url=url, status=response.status_code)
            raise HTTPException(status_code=502, detail=f"Webhook delivery failed: {response.status_code}")

        logger.info("webhook_dispatched", event=event_type, url=url)
        return {"status": "delivered", "event": event_type}


class IntegrationRouter:
    """Route agent events to configured integrations."""

    def __init__(self):
        self.webhooks: dict[str, str] = {}
        self.dispatcher = WebhookDispatcher()

    def register_webhook(self, event_type: str, url: str) -> None:
        self.webhooks[event_type] = url

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

    async def _emit(self, event_type: str, data: dict) -> None:
        url = self.webhooks.get(event_type)
        if url:
            await self.dispatcher.dispatch(url, event_type, data)
