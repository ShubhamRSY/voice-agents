"""Amazon Connect telephony adapter — Lambda-style webhook integration.

Amazon Connect contact flows invoke this handler via the "Invoke AWS Lambda"
or "External HTTP" block.  The expected payload shape follows the Lambda event
format documented at:
  https://docs.aws.amazon.com/connect/latest/adminguide/connect-lambda-functions.html
"""

import json
import time
from typing import Any

import structlog
from fastapi import Request, Response

from src.telephony.ccaas_base import CallFormData, CcaasSessionEntry, CcaasVoiceHandler
from src.workflows.orchestrator import AgentOrchestrator

logger = structlog.get_logger()


class AmazonConnectVoiceHandler(CcaasVoiceHandler):
    """Handles voice calls routed via Amazon Connect contact flows."""

    def __init__(self, agent_id: str = "voice_support", session_ttl_seconds: int = 7200):
        from src.config import get_settings, load_agent_config

        self.agent_id = agent_id
        self.config = load_agent_config()["agents"][agent_id]
        self.telephony_config = self.config.get("telephony", {})
        self.settings = get_settings()
        self.session_ttl_seconds = session_ttl_seconds
        self.sessions: dict[str, CcaasSessionEntry] = {}

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _parse_payload(self, body: dict) -> CallFormData:
        """Extract call data from an Amazon Connect Lambda event payload."""
        details = body.get("Details", {})
        contact_data = details.get("ContactData", {})
        attributes = details.get("Attributes", {})

        call_sid = contact_data.get("ContactId", body.get("ContactId", "unknown"))
        customer_endpoint = contact_data.get("CustomerEndpoint", {})
        from_number = customer_endpoint.get("Address", attributes.get("fromNumber", "anonymous"))
        speech_result = attributes.get("SpeechResult") or body.get("SpeechResult")

        return CallFormData(
            call_sid=call_sid,
            from_number=from_number,
            speech_result=speech_result,
        )

    def _get_orchestrator(self, call_sid: str) -> AgentOrchestrator:
        self._evict_stale_sessions()
        entry = self.sessions.get(call_sid)
        if entry is None:
            entry = CcaasSessionEntry(orchestrator=AgentOrchestrator(self.agent_id))
            self.sessions[call_sid] = entry
        entry.last_access = time.time()
        return entry.orchestrator

    def _evict_stale_sessions(self) -> None:
        now = time.time()
        stale = [
            sid
            for sid, entry in self.sessions.items()
            if now - entry.last_access > self.session_ttl_seconds
        ]
        for sid in stale:
            del self.sessions[sid]

    def _connect_response(
        self,
        message: str,
        transfer: bool = False,
        transfer_phone: str | None = None,
    ) -> dict:
        """Build a response dict that Amazon Connect contact flows consume.

        The contact flow reads `result[`message`]` for TTS playback and
        `result[`transfer_requested`]` for branching.
        """
        return {
            "message": message,
            "transfer_requested": transfer,
            "transfer_phone": transfer_phone or "",
            "agent_id": self.agent_id,
        }

    # -------------------------------------------------------------------
    # Public handlers
    # -------------------------------------------------------------------

    async def handle_inbound(self, request: Request) -> Response:
        """Initial inbound — greet caller and wait for speech.

        Amazon Connect invokes this at the start of a contact flow.
        """
        body = await request.json()
        data = self._parse_payload(body)

        # If Amazon Connect already captures speech via "Get customer input"
        # and passes it as an attribute, process it directly.
        if data.speech_result:
            return await self.handle_process(request)

        greeting = self.telephony_config.get("greeting", "Hello, how can I help you?")
        logger.info("connect_inbound_greeting", contact_id=data.call_sid, from_number=data.from_number)
        return Response(
            content=json.dumps(self._connect_response(greeting)),
            media_type="application/json",
        )

    async def handle_process(self, request: Request) -> Response:
        """Process speech from a "Get customer input" block or Follow-up flow."""
        body = await request.json()
        data = self._parse_payload(body)

        if not data.speech_result:
            fallback = self.telephony_config.get("fallback_message", "I didn't catch that.")
            return Response(
                content=json.dumps(self._connect_response(fallback)),
                media_type="application/json",
            )

        orchestrator = self._get_orchestrator(data.call_sid)
        customer_info = f"Caller phone: {data.from_number}"

        result = await orchestrator.invoke(
            user_input=data.speech_result,
            customer_info=customer_info,
        )

        agent_response = result["response"]
        transfer_requested = any(
            tc.get("name") == "transfer_to_human" for tc in result.get("tool_calls", [])
        )

        transfer_number = self.telephony_config.get("transfer_number", "")

        logger.info(
            "connect_speech_processed",
            contact_id=data.call_sid,
            from_number=data.from_number,
            transfer=transfer_requested,
        )

        return Response(
            content=json.dumps(self._connect_response(
                message=agent_response,
                transfer=transfer_requested,
                transfer_phone=transfer_number if transfer_requested else None,
            )),
            media_type="application/json",
        )

    async def handle_status_callback(self, request: Request) -> dict[str, Any]:
        """Handle Amazon Connect Contact Flow event callbacks."""
        body = await request.json()
        contact_id = body.get("ContactId", body.get("Details", {}).get("ContactData", {}).get("ContactId", ""))
        status = body.get("Status", body.get("EventType", "unknown"))

        if status in ("COMPLETED", "FAILED", "CANCELLED", "DISCONNECTED"):
            self.sessions.pop(contact_id, None)
            logger.info("connect_call_ended", contact_id=contact_id, status=status)

        return {"status": "ok"}

    async def simulate(
        self,
        call_sid: str,
        from_number: str,
        speech_result: str | None = None,
    ) -> str:
        """Simulate an Amazon Connect webhook request without a real call."""

        class _MockRequest:
            def __init__(self, payload: dict):
                self._payload = payload

            async def json(self):
                return self._payload

        payload: dict[str, Any] = {
            "Details": {
                "ContactData": {
                    "ContactId": call_sid,
                    "CustomerEndpoint": {"Address": from_number},
                    "SystemEndpoint": {"Address": "+15551234567"},
                    "Attributes": {},
                },
                "Attributes": {},
            },
        }
        if speech_result:
            payload["Details"]["Attributes"]["SpeechResult"] = speech_result
            payload["SpeechResult"] = speech_result

        mock = _MockRequest(payload)
        if speech_result:
            response = await self.handle_process(mock)
        else:
            response = await self.handle_inbound(mock)
        return response.body.decode("utf-8")
