"""WhatsApp/SMS messaging channel via Twilio Messaging API."""

import hashlib

import httpx
import structlog
from fastapi import HTTPException

from src.config import get_settings
from src.database import db
from src.request_context import set_request_context

logger = structlog.get_logger()


class WhatsAppMessenger:
    """Send and receive WhatsApp/SMS messages via Twilio."""

    TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

    def __init__(self):
        settings = get_settings()
        self.account_sid = settings.twilio_account_sid
        self.auth_token = settings.twilio_auth_token
        self.phone_number = settings.twilio_phone_number

    def _is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.phone_number)

    def _auth(self) -> httpx.BasicAuth:
        return httpx.BasicAuth(self.account_sid, self.auth_token)

    async def send_message(self, to: str, body: str, channel: str = "whatsapp") -> dict:
        """Send a WhatsApp or SMS message.

        For WhatsApp, 'to' should be 'whatsapp:+15551234567'.
        For SMS, 'to' should be '+15551234567'.
        """
        if not self._is_configured():
            logger.info("whatsapp_mock_send", to=to, body=body[:50])
            return {"status": "mock_sent", "to": to, "body_preview": body[:80]}

        url = f"{self.TWILIO_API_BASE}/Accounts/{self.account_sid}/Messages.json"

        from_number = f"whatsapp:{self.phone_number}" if channel == "whatsapp" else self.phone_number

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                auth=self._auth(),
                data={
                    "From": from_number,
                    "To": to,
                    "Body": body,
                },
            )

            if resp.status_code not in (200, 201):
                logger.error("twilio_message_failed", status=resp.status_code, body=resp.text)
                raise HTTPException(status_code=502, detail=f"Twilio message failed: {resp.status_code}")

            data = resp.json()
            logger.info("twilio_message_sent", sid=data.get("sid"), to=to)
            return {
                "sid": data.get("sid"),
                "status": data.get("status"),
                "to": to,
                "from": from_number,
            }

    async def handle_inbound_webhook(self, form_data: dict) -> dict:
        """Process incoming WhatsApp/SMS webhook from Twilio and reply via AI or queue."""
        from src.api.deps import get_session as get_orch_session
        from src.integrations.translation import detect_locale, localize_response, translate_text

        from_number = form_data.get("From", "")
        to_number = form_data.get("To", "")
        body = form_data.get("Body", "")
        message_sid = form_data.get("MessageSid", "")

        channel = "whatsapp" if "whatsapp:" in from_number else "sms"
        tenant_id = "default"
        session_id = f"msg-{hashlib.md5(from_number.encode(), usedforsecurity=False).hexdigest()[:12]}"
        locale = detect_locale(body)

        logger.info("incoming_message", channel=channel, from_=from_number, body=body[:100])

        if not db.get_session(session_id):
            db.create_session(session_id, tenant_id, "chat_support", channel, from_number)
        db.update_session_locale(session_id, locale)

        translated = await translate_text(body, target_locale="en", source_locale=locale)
        inbound_text = translated["text"]

        set_request_context(session_id=session_id, tenant_id=tenant_id)
        orch = get_orch_session(session_id, "chat_support", tenant_id)
        result = await orch.invoke(user_input=inbound_text, customer_info=from_number)
        db.save_message(session_id, "user", body)
        db.save_message(session_id, "assistant", result["response"], tool_calls=result.get("tool_calls", []))

        session = db.get_session(session_id) or {}
        reply = result["response"]
        if session.get("handoff_status") == "queued":
            reply = "Thanks for your message. A specialist will respond shortly."
        else:
            reply = await localize_response(reply, locale)

        send_result = await self.send_message(from_number, reply, channel)

        return {
            "message_sid": message_sid,
            "from": from_number,
            "to": to_number,
            "body": body,
            "channel": channel,
            "session_id": session_id,
            "response": reply,
            "send": send_result,
        }
