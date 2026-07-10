"""Telephony, voice, messaging, and SSE streaming routes."""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from structlog import get_logger

from src.config import get_settings
from src.workflows.orchestrator import AgentOrchestrator
from src.telephony.call_router import CallMetadata
from src.telephony.stt import transcribe_audio
from src.telephony.tts import synthesize_speech
from src.telephony.security import require_twilio_signature
from src.telephony.twiml_parser import parse_twiml
from src.api.deps import (
    VoiceSimulateRequest, SpeakRequest,
    _call_router, voice_handler, whatsapp,
    require_auth,
)
from src.saas.plan_gates import require_channel_for_context

logger = get_logger()
router = APIRouter()


# ---------------------------------------------------------------------------
# Twilio voice webhooks
# ---------------------------------------------------------------------------

@router.post("/telephony/voice/inbound")
async def voice_inbound(
    request: Request,
    _: None = Depends(require_twilio_signature),
):
    return await voice_handler.handle_inbound(request)


@router.post("/telephony/voice/process")
async def voice_process(
    request: Request,
    _: None = Depends(require_twilio_signature),
):
    return await voice_handler.handle_process(request)


@router.post("/telephony/voice/status")
async def voice_status(
    request: Request,
    _: None = Depends(require_twilio_signature),
) -> dict[str, Any]:
    return await voice_handler.handle_status_callback(request)


# ---------------------------------------------------------------------------
# STT / TTS
# ---------------------------------------------------------------------------

@router.post("/telephony/transcribe")
async def transcribe_voice(ctx: Any = Depends(require_auth), audio: UploadFile = File(...)) -> dict[str, str]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="Server transcription requires OPENAI_API_KEY. Type caller speech and tap Send.",
        )

    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio recording.")

    text = await asyncio.to_thread(
        transcribe_audio,
        content,
        audio.filename or "speech.webm",
    )
    if not text:
        raise HTTPException(status_code=422, detail="Could not transcribe audio. Speak longer and try again.")

    return {"text": text}


@router.post("/telephony/speak")
async def speak_agent(request: SpeakRequest, ctx: Any = Depends(require_auth)) -> Response:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="TTS requires OPENAI_API_KEY.")

    audio = await asyncio.to_thread(synthesize_speech, request.text, request.voice)
    if not audio:
        raise HTTPException(status_code=400, detail="Nothing to speak.")

    return Response(content=audio, media_type="audio/mpeg")


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@router.post("/telephony/simulate")
async def telephony_simulate(request: VoiceSimulateRequest, ctx: Any = Depends(require_auth)) -> dict[str, Any]:
    require_channel_for_context(ctx, "voice")
    sip_meta = _call_router.extract_sip_headers(request.sip_headers)
    metadata = CallMetadata(
        call_sid=request.call_sid,
        from_number=request.from_number,
        to_number="+1800ACME",
        custom_fields=sip_meta,
    )
    route_destination = _call_router.route(metadata)

    twiml = await voice_handler.simulate(
        call_sid=request.call_sid,
        from_number=request.from_number,
        speech_result=request.speech,
    )
    parsed = parse_twiml(twiml)

    return {
        "call_sid": request.call_sid,
        "from_number": request.from_number,
        "caller_said": request.speech,
        "agent_says": parsed["agent_says"],
        "agent_response": parsed.get("agent_response", ""),
        "spoken_responses": parsed["spoken_responses"],
        "transfer_to": parsed["transfer_to"],
        "listening": parsed["listening"],
        "call_actions": parsed["actions"],
        "routing": {
            "destination": route_destination,
            "sip_headers": sip_meta,
            "strategy": "skill_based",
        },
        "twiml": twiml,
    }


# ---------------------------------------------------------------------------
# SSE streaming for voice
# ---------------------------------------------------------------------------

@router.get("/telephony/voice/stream")
async def voice_stream_sse(request: Request):
    """SSE endpoint — streams agent response tokens one-by-one. Accept ?speech=<text>."""
    async def event_stream():
        speech = request.query_params.get("speech", "").strip()
        if not speech:
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Voice stream ready. Send ?speech=<text> to interact.'})}\n\n"
            while True:
                await asyncio.sleep(1)
                if await request.is_disconnected():
                    break
            return

        yield f"data: {json.dumps({'type': 'transcribing', 'text': speech})}\n\n"

        orchestrator = AgentOrchestrator("voice_support")
        final_result = None

        async for event in orchestrator.invoke_stream(
            user_input=speech,
            customer_info="Caller via SSE stream",
        ):
            if await request.is_disconnected():
                break
            if event["type"] == "token":
                yield f"data: {json.dumps({'type': 'token', 'content': event['content']})}\n\n"
            elif event["type"] == "done":
                final_result = event

        if final_result:
            yield f"data: {json.dumps({'type': 'done', **final_result})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


# ---------------------------------------------------------------------------
# WhatsApp / SMS
# ---------------------------------------------------------------------------

@router.post("/messaging/inbound")
async def messaging_inbound(request: Request) -> dict:
    form = await request.form()
    return await whatsapp.handle_inbound_webhook(dict(form))


@router.post("/messaging/send")
async def messaging_send(ctx: Any = Depends(require_auth), to: str = "", body: str = "", channel: str = "whatsapp") -> dict:
    require_channel_for_context(ctx, channel)
    return await whatsapp.send_message(to, body, channel)
