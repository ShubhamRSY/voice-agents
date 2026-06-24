"""Twilio telephony integration for voice agents."""

import time
from typing import Any

import structlog
from fastapi import Request, Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from src.config import get_settings, load_agent_config
from src.telephony.ccaas_base import CallFormData, CcaasSessionEntry, CcaasVoiceHandler
from src.workflows.orchestrator import AgentOrchestrator

logger = structlog.get_logger()


class TwilioVoiceHandler(CcaasVoiceHandler):
    """Handles inbound/outbound Twilio voice calls with SIP/PSTN routing."""

    def __init__(self, agent_id: str = "voice_support", session_ttl_seconds: int = 7200):
        self.agent_id = agent_id
        self.config = load_agent_config()["agents"][agent_id]
        self.telephony_config = self.config.get("telephony", {})
        self.settings = get_settings()
        self.session_ttl_seconds = session_ttl_seconds
        self.sessions: dict[str, CcaasSessionEntry] = {}

    async def _parse_form(self, request: Request) -> CallFormData:
        form = await request.form()
        speech = form.get("SpeechResult")
        return CallFormData(
            call_sid=str(form.get("CallSid", "")),
            from_number=str(form.get("From", "")),
            speech_result=str(speech) if speech else None,
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

    def _webhook_url(self, path: str) -> str:
        base = self.settings.twilio_webhook_base_url.rstrip("/")
        return f"{base}{path}"

    def _build_gather(self, prompt_text: str) -> Gather:
        gather = Gather(
            input="speech",
            action=self._webhook_url("/telephony/voice/process"),
            method="POST",
            speech_timeout=str(self.telephony_config.get("max_silence_seconds", 5)),
            language="en-US",
        )
        gather.say(prompt_text)
        return gather

    async def handle_inbound(self, request: Request) -> Response:
        """Initial PSTN inbound — greet caller and start speech gather."""
        data = await self._parse_form(request)

        if data.speech_result:
            return await self.handle_process(request, data)

        response = VoiceResponse()
        gather = self._build_gather(
            self.telephony_config.get("greeting", "Hello, how can I help you?")
        )
        response.append(gather)
        response.say(self.telephony_config.get("fallback_message", "I didn't catch that."))
        response.redirect(self._webhook_url("/telephony/voice/inbound"))

        logger.info("voice_inbound_greeting", call_sid=data.call_sid, from_number=data.from_number)
        return Response(content=str(response), media_type="application/xml")

    async def handle_process(self, request: Request, data: CallFormData | None = None) -> Response:
        """Process caller speech from Gather webhook — invoke agent and respond."""
        if data is None:
            data = await self._parse_form(request)

        response = VoiceResponse()

        if not data.speech_result:
            gather = self._build_gather(
                self.telephony_config.get("fallback_message", "I didn't catch that. Please try again.")
            )
            response.append(gather)
            response.redirect(self._webhook_url("/telephony/voice/process"))
            return Response(content=str(response), media_type="application/xml")

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

        if transfer_requested:
            transfer_number = self.telephony_config.get("transfer_number", "")
            response.say("Let me connect you with a specialist. One moment please.")
            if transfer_number:
                response.dial(transfer_number)
            else:
                response.say("All agents are currently busy. Please try again later.")
        else:
            gather = self._build_gather(agent_response)
            response.append(gather)
            response.say("Is there anything else I can help with?")
            response.redirect(self._webhook_url("/telephony/voice/inbound"))

        logger.info(
            "voice_speech_processed",
            call_sid=data.call_sid,
            from_number=data.from_number,
            transfer=transfer_requested,
        )
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
            def __init__(self, payload: CallFormData):
                self._payload = payload

            async def form(self):
                data: dict[str, str] = {
                    "CallSid": self._payload.call_sid,
                    "From": self._payload.from_number,
                }
                if self._payload.speech_result:
                    data["SpeechResult"] = self._payload.speech_result
                return data

        payload = CallFormData(call_sid=call_sid, from_number=from_number, speech_result=speech_result)
        mock = _MockRequest(payload)
        if speech_result:
            response = await self.handle_process(mock, payload)
        else:
            response = await self.handle_inbound(mock)
        return response.body.decode("utf-8")
