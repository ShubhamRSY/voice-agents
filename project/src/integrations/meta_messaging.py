"""Meta Messenger and Instagram Direct messaging via Graph API."""

from __future__ import annotations

import hashlib
import hmac

import httpx
import structlog

from src.config import get_settings
from src.database import db
from src.request_context import set_request_context

logger = structlog.get_logger()

GRAPH_API = "https://graph.facebook.com/v19.0"


class MetaMessenger:
    def _configured(self) -> bool:
        return bool(get_settings().meta_page_access_token)

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        secret = get_settings().meta_app_secret
        if not secret or not signature.startswith("sha256="):
            return not secret
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    async def send_message(self, recipient_id: str, text: str, channel: str = "messenger") -> dict:
        settings = get_settings()
        if not self._configured():
            logger.info("meta_mock_send", to=recipient_id, channel=channel)
            return {"status": "mock_sent", "recipient_id": recipient_id, "channel": channel}

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{GRAPH_API}/me/messages",
                params={"access_token": settings.meta_page_access_token},
                json={
                    "recipient": {"id": recipient_id},
                    "message": {"text": text},
                    "messaging_type": "RESPONSE",
                },
            )
            if resp.status_code not in (200, 201):
                logger.error("meta_send_failed", status=resp.status_code, body=resp.text[:200])
                return {"status": "failed", "error": resp.text[:200]}
            return {"status": "sent", "data": resp.json(), "channel": channel}

    async def handle_webhook(self, payload: dict) -> dict:
        from src.api.deps import get_session as get_orch_session
        from src.integrations.translation import detect_locale, localize_response, translate_text

        results = []
        obj_type = payload.get("object", "page")
        channel = "instagram" if obj_type == "instagram" else "messenger"
        tenant_id = "default"

        for entry in payload.get("entry", []):
            for event in entry.get("messaging", []):
                sender = event.get("sender", {}).get("id", "")
                message = event.get("message", {})
                body = message.get("text", "")
                if not body or message.get("is_echo"):
                    continue

                session_id = f"meta-{channel}-{hashlib.md5(sender.encode(), usedforsecurity=False).hexdigest()[:10]}"
                locale = detect_locale(body)

                if not db.get_session(session_id):
                    db.create_session(session_id, tenant_id, "chat_support", channel, sender)
                db.update_session_locale(session_id, locale)

                translated = await translate_text(body, target_locale="en", source_locale=locale)
                set_request_context(session_id=session_id, tenant_id=tenant_id)
                orch = get_orch_session(session_id, "chat_support", tenant_id)
                result = await orch.invoke(user_input=translated["text"], customer_info=sender)
                db.save_message(session_id, "user", body)

                session = db.get_session(session_id) or {}
                reply = result["response"]
                if session.get("handoff_status") == "queued":
                    reply = "Thanks for your message. A specialist will respond shortly."
                else:
                    reply = await localize_response(reply, locale)

                msg_row = db.save_message(
                    session_id, "assistant", reply,
                    tool_calls=result.get("tool_calls", []),
                    metrics=result.get("metrics", {}),
                )
                send = await self.send_message(sender, reply, channel)
                results.append({
                    "session_id": session_id,
                    "channel": channel,
                    "sender": sender,
                    "response": reply,
                    "message_id": msg_row if isinstance(msg_row, int) else None,
                    "send": send,
                })

        return {"processed": len(results), "events": results}


meta_messenger = MetaMessenger()
