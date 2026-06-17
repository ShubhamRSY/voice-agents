"""Twilio telephony integration for voice agents."""

from typing import Any

import structlog
from fastapi import Request, Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from src.config import get_settings, load_agent_config
from src.workflows.orchestrator import AgentOrchestrator

logger = structlog.get_logger()


class TwilioVoiceHandler:
    """Handles inbound/outbound Twilio voice calls with SIP/PSTN routing."""

    def __init__(self, agent_id: str = "voice_support"):
        self.agent_id = agent_id
        self.config = load_agent_config()["agents"][agent_id]
        self.telephony_config = self.config.get("telephony", {})
        self.settings = get_settings()
        self.sessions: dict[str, AgentOrchestrator] = {}

    def _get_orchestrator(self, call_sid: str) -> AgentOrchestrator:
        if call_sid not in self.sessions:
            self.sessions[call_sid] = AgentOrchestrator(self.agent_id)
        return self.sessions[call_sid]

    def _webhook_url(self, path: str) -> str:
        base = self.settings.twilio_webhook_base_url.rstrip("/")
        return f"{base}{path}"

    async def handle_inbound(self, request: Request) -> Response:
        form = await request.form()
        call_sid = str(form.get("CallSid", ""))
        from_number = str(form.get("From", ""))
        speech_result = form.get("SpeechResult")

        response = VoiceResponse()

        if not speech_result:
            gather = Gather(
                input="speech",
                action=self._webhook_url("/telephony/voice/process"),
                method="POST",
                speech_timeout=str(self.telephony_config.get("max_silence_seconds", 5)),
                language="en-US",
            )
            gather.say(self.telephony_config.get("greeting", "Hello, how can I help you?"))
            response.append(gather)
            response.say(self.telephony_config.get("fallback_message", "I didn't catch that."))
            response.redirect(self._webhook_url("/telephony/voice/inbound"))
            return Response(content=str(response), media_type="application/xml")

        orchestrator = self._get_orchestrator(call_sid)
        customer_info = f"Caller phone: {from_number}"

        result = await orchestrator.invoke(
            user_input=str(speech_result),
            customer_info=customer_info,
        )

        agent_response = result["response"]
        transfer_requested = any(
            tc.get("name") == "transfer_to_human" for tc in result.get("tool_calls", [])
        )

        if transfer_requested:
            transfer_number = self.telephony_config.get("transfer_number", "")
            response.say("Let me connect you with a specialist. One moment please.")
            if transfer_number:
                response.dial(transfer_number)
            else:
                response.say("All agents are currently busy. Please try again later.")
        else:
            gather = Gather(
                input="speech",
                action=self._webhook_url("/telephony/voice/process"),
                method="POST",
                speech_timeout="5",
                language="en-US",
            )
            gather.say(agent_response)
            response.append(gather)
            response.say("Is there anything else I can help with?")
            response.redirect(self._webhook_url("/telephony/voice/inbound"))

        logger.info("voice_call_processed", call_sid=call_sid, from_number=from_number)
        return Response(content=str(response), media_type="application/xml")

    async def handle_status_callback(self, request: Request) -> dict[str, Any]:
        form = await request.form()
        call_sid = str(form.get("CallSid", ""))
        call_status = str(form.get("CallStatus", ""))

        if call_status in ("completed", "failed", "busy", "no-answer"):
            self.sessions.pop(call_sid, None)
            logger.info("call_ended", call_sid=call_sid, status=call_status)

        return {"status": "ok"}

    def generate_outbound_twiml(self, message: str) -> str:
        response = VoiceResponse()
        response.say(message)
        return str(response)

    async def simulate(
        self,
        call_sid: str,
        from_number: str,
        speech_result: str | None = None,
    ) -> str:
        """Simulate a Twilio webhook request without a real phone call."""

        class _MockRequest:
            async def form(self_inner):
                data = {"CallSid": call_sid, "From": from_number}
                if speech_result:
                    data["SpeechResult"] = speech_result
                return data

        response = await self.handle_inbound(_MockRequest())
        return response.body.decode("utf-8")
