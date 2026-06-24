"""FastAPI routes for chat, voice, copilot, RAG, evaluation, auth, KB, analytics, and more."""

import asyncio
import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.analytics import analytics
from src.api.session_manager import SessionManager
from src.auth import (
    AuthContext,
    create_jwt,
    get_auth_context,
    hash_password,
    require_auth,
    verify_password,
)
from src.config import Settings, get_settings, reload_settings
from src.database import db
from src.evaluation.evaluator import AgentEvaluator
from src.feedback.engine import FeedbackEngine

from src.integrations.secrets_vault import CREDENTIAL_KEYS, WEBHOOK_EVENTS, get_secrets_vault
from src.integrations.webhooks import IntegrationRouter
from src.integrations.whatsapp import WhatsAppMessenger
from src.rag.ingestion import ingest_directory, ingest_file
from src.rag.vector_store import VectorStore
from src.tasks import task_queue
from src.integrations.slack import SlackNotifier
from src.integrations.zendesk import ZendeskClient
from src.integrations.servicenow import ServiceNowClient
from src.observability import collector
from src.telephony.call_router import CallMetadata, CallRouter, RoutingRule
from src.telephony.stt import transcribe_audio
from src.telephony.tts import DEFAULT_VOICE, synthesize_speech
from src.telephony.twilio_handler import TwilioVoiceHandler
from src.telephony.twiml_parser import parse_twiml
from src.workflows.orchestrator import AgentOrchestrator

logger = structlog.get_logger()
router = APIRouter()
integration_router = IntegrationRouter()
voice_handler = TwilioVoiceHandler()
whatsapp = WhatsAppMessenger()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    agent_id: str = "chat_support"
    customer_info: str = ""
    session_id: str = ""


class ChatResponse(BaseModel):
    response: str
    agent_id: str
    tool_calls: list[dict] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)


class CopilotRequest(BaseModel):
    message: str
    conversation_summary: str = ""
    agent_id: str = "copilot"


class IngestRequest(BaseModel):
    source_path: str


class WebhookRegisterRequest(BaseModel):
    event_type: str
    url: str


class CredentialsUpdateRequest(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    twilio_webhook_base_url: str | None = None
    hubspot_api_key: str | None = None
    salesforce_client_id: str | None = None
    salesforce_client_secret: str | None = None
    webhook_signing_secret: str | None = None


class VoiceSimulateRequest(BaseModel):
    call_sid: str = "SIM-CALL-001"
    from_number: str = "+15551234567"
    speech: str | None = None
    sip_headers: dict[str, str] = Field(default_factory=dict)


class SpeakRequest(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    tenant_name: str = "My Organization"


class ArticleCreateRequest(BaseModel):
    title: str
    content: str
    tags: str = ""
    category: str = "general"


class ArticleUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: str | None = None
    category: str | None = None


class CSATRequest(BaseModel):
    session_id: str
    score: int
    feedback: str = ""


class WebhookEventRequest(BaseModel):
    event_type: str
    payload: dict = Field(default_factory=dict)


_call_router = CallRouter()
_call_router.add_rule(RoutingRule("vip", "from:+1555", "+15559999999", priority=10))
_call_router.set_fallback("+15551111111")


_sessions = SessionManager(ttl_seconds=3600, max_sessions=1000)


def _get_session(session_id: str, agent_id: str, tenant_id: str = "default") -> AgentOrchestrator:
    return _sessions.get(session_id, agent_id)


async def _require_auth(ctx: AuthContext | None = Depends(get_auth_context)) -> AuthContext | None:
    """Require auth when the platform is configured for it, otherwise allow anonymous."""
    from src.config import get_settings
    if get_settings().auth_required:
        if ctx is None:
            raise HTTPException(status_code=401, detail="Authentication required")
    return ctx


def _require_settings_token(request: Request) -> None:
    token = get_settings().settings_admin_token.strip()
    if not token:
        return
    provided = request.headers.get("X-Settings-Token", "")
    if provided != token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Settings-Token header.")


def _env_credentials() -> dict[str, str]:
    env_settings = Settings()
    return {key: getattr(env_settings, key, "") or "" for key in CREDENTIAL_KEYS}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "healthy",
        "service": "enterprise-voice-agents",
        "stt_available": bool(settings.openai_api_key),
        "tts_available": bool(settings.openai_api_key),
        "tts_voice": DEFAULT_VOICE,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.post("/auth/login")
async def login(request: LoginRequest) -> dict[str, Any]:
    user = db.get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    db.update_last_login(user["id"])
    token = create_jwt({
        "sub": user["id"],
        "tenant_id": user["tenant_id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    })
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        },
    }


@router.post("/auth/register")
async def register(request: RegisterRequest) -> dict[str, Any]:
    tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"
    user_id = f"user-{uuid.uuid4().hex[:8]}"

    existing = db.get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    db.create_tenant(tenant_id, request.tenant_name, tenant_id)
    db.create_user(user_id, tenant_id, request.email, hash_password(request.password), request.name, "admin")
    db.log_audit(tenant_id, user_id, "tenant.created", "tenant", {"tenant_name": request.tenant_name})

    token = create_jwt({
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": request.email,
        "name": request.name,
        "role": "admin",
    })
    return {"token": token, "tenant_id": tenant_id, "user_id": user_id}


@router.get("/auth/me")
async def me(ctx: AuthContext = Depends(require_auth)) -> dict:
    return {
        "user_id": ctx.user_id,
        "tenant_id": ctx.tenant_id,
        "email": ctx.email,
        "name": ctx.name,
        "role": ctx.role,
        "is_admin": ctx.is_admin(),
    }


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, ctx: AuthContext | None = Depends(_require_auth)) -> ChatResponse:
    from src.config import load_agent_config
    agent_config = load_agent_config()
    if request.agent_id not in agent_config.get("agents", {}):
        raise HTTPException(status_code=400, detail=f"Unknown agent: {request.agent_id}")

    tenant_id = ctx.tenant_id if ctx else "default"
    session_id = request.session_id or f"session-{uuid.uuid4().hex[:12]}"
    orchestrator = _get_session(session_id, request.agent_id, tenant_id)

    result = await orchestrator.invoke(
        user_input=request.message,
        customer_info=request.customer_info or "No customer identified",
    )

    existing = db.get_session(session_id)
    if not existing:
        db.create_session(session_id, tenant_id, request.agent_id, "chat", request.customer_info)
    db.save_message(session_id, "user", request.message)
    db.save_message(
        session_id, "assistant", result["response"],
        tool_calls=result.get("tool_calls", []),
        metrics=result.get("metrics", {}),
    )
    db.log_audit(tenant_id, ctx.user_id if ctx else None, "chat.message", "session", {
        "session_id": session_id, "agent_id": request.agent_id,
    })

    await integration_router.on_conversation_start(session_id, "chat", {
        "agent_id": request.agent_id, "tenant_id": tenant_id,
    })

    return ChatResponse(
        response=result["response"],
        agent_id=result["agent_id"],
        tool_calls=result.get("tool_calls", []),
        metrics=result.get("metrics", {}),
    )


# ---------------------------------------------------------------------------
# Copilot
# ---------------------------------------------------------------------------

@router.post("/copilot")
async def copilot(request: CopilotRequest, ctx: AuthContext | None = Depends(_require_auth)) -> dict[str, Any]:
    orchestrator = AgentOrchestrator(request.agent_id)
    result = await orchestrator.invoke(
        user_input=request.message,
        extra_context=request.conversation_summary,
    )
    return result


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.delete("/chat/{session_id}")
async def end_session(session_id: str) -> dict[str, str]:
    _sessions.remove(session_id)
    db.end_session(session_id)
    await integration_router.on_conversation_end(session_id, "completed", {})
    return {"status": "session_ended"}


@router.get("/sessions/stats")
async def session_stats() -> dict[str, int]:
    _sessions.evict_stale()
    return {"active_sessions": _sessions.active_count}


@router.get("/sessions/{session_id}/history")
async def session_history(session_id: str) -> dict:
    messages = db.get_session_messages(session_id)
    session_info = db.get_session(session_id)
    return {"session": session_info, "messages": messages}


# ---------------------------------------------------------------------------
# Knowledge Base Management
# ---------------------------------------------------------------------------

@router.get("/kb/articles")
async def list_articles(category: str | None = None, ctx: AuthContext = Depends(require_auth)) -> dict:
    articles = db.list_articles(ctx.tenant_id, category)
    return {"articles": articles, "count": len(articles)}


@router.get("/kb/articles/{article_id}")
async def get_article(article_id: int, ctx: AuthContext = Depends(require_auth)) -> dict:
    article = db.get_article(article_id, ctx.tenant_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"article": article}


@router.post("/kb/articles")
async def create_article(body: ArticleCreateRequest, ctx: AuthContext = Depends(require_auth)) -> dict:
    result = db.create_article(ctx.tenant_id, body.title, body.content, body.tags, body.category)
    db.log_audit(ctx.tenant_id, ctx.user_id, "kb.article.created", f"article/{result['id']}", body.model_dump())
    return {"status": "created", "article": result}


@router.put("/kb/articles/{article_id}")
async def update_article(article_id: int, body: ArticleUpdateRequest, ctx: AuthContext = Depends(require_auth)) -> dict:
    result = db.update_article(article_id, ctx.tenant_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Article not found")
    db.log_audit(ctx.tenant_id, ctx.user_id, "kb.article.updated", f"article/{article_id}", body.model_dump(exclude_unset=True))
    return {"status": "updated", "article": result}


@router.delete("/kb/articles/{article_id}")
async def delete_article(article_id: int, ctx: AuthContext = Depends(require_auth)) -> dict:
    if not db.delete_article(article_id, ctx.tenant_id):
        raise HTTPException(status_code=404, detail="Article not found")
    db.log_audit(ctx.tenant_id, ctx.user_id, "kb.article.deleted", f"article/{article_id}", {})
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# CSAT Surveys
# ---------------------------------------------------------------------------

@router.post("/csat")
async def submit_csat(body: CSATRequest) -> dict:
    session = db.get_session(body.session_id)
    tenant_id = session["tenant_id"] if session else "default"
    try:
        result = db.save_csat(body.session_id, tenant_id, body.score, body.feedback)
    except Exception as exc:
        logger.warning("csat_save_failed", session_id=body.session_id, error=str(exc))
        result = {"id": 0, "session_id": body.session_id, "score": body.score}
    logger.info("csat_submitted", session_id=body.session_id, score=body.score)
    return {"status": "recorded", "csat": result}


@router.get("/csat/stats")
async def csat_stats(ctx: AuthContext | None = Depends(_require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    return {"stats": db.get_csat_stats(tenant_id)}


# ---------------------------------------------------------------------------
# Analytics Dashboard
# ---------------------------------------------------------------------------

@router.get("/analytics/dashboard")
async def analytics_dashboard(hours: int = 24, ctx: AuthContext = Depends(require_auth)) -> dict:
    return {"dashboard": analytics.get_dashboard(ctx.tenant_id, hours)}


@router.get("/analytics/agents")
async def analytics_agents(hours: int = 168, ctx: AuthContext = Depends(require_auth)) -> dict:
    return {"scorecard": analytics.get_agent_scorecard(ctx.tenant_id, hours)}


@router.get("/analytics/timeline")
async def analytics_timeline(hours: int = 24, ctx: AuthContext = Depends(require_auth)) -> dict:
    return {"timeline": analytics.get_conversation_timeline(ctx.tenant_id, hours)}


@router.get("/analytics/audit-log")
async def audit_log(limit: int = 100, ctx: AuthContext = Depends(require_auth)) -> dict:
    return {"logs": db.get_audit_logs(ctx.tenant_id, limit)}


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------

@router.post("/rag/ingest")
async def ingest_documents(request: IngestRequest) -> dict[str, Any]:
    from pathlib import Path

    path = Path(request.source_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    if path.is_dir():
        count = ingest_directory(path)
    else:
        count = ingest_file(path)

    return {"ingested_chunks": count, "source": str(path)}


@router.post("/rag/search")
async def search_knowledge(query: str, top_k: int = 5) -> dict[str, Any]:
    store = VectorStore()
    results = store.similarity_search(query, k=top_k)
    return {"query": query, "results": results}


# ---------------------------------------------------------------------------
# Telephony
# ---------------------------------------------------------------------------

@router.post("/telephony/voice/inbound")
async def voice_inbound(request: Request):
    return await voice_handler.handle_inbound(request)


@router.post("/telephony/voice/process")
async def voice_process(request: Request):
    return await voice_handler.handle_process(request)


@router.post("/telephony/voice/status")
async def voice_status(request: Request) -> dict[str, Any]:
    return await voice_handler.handle_status_callback(request)


@router.post("/telephony/transcribe")
async def transcribe_voice(ctx: AuthContext | None = Depends(_require_auth), audio: UploadFile = File(...)) -> dict[str, str]:
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
async def speak_agent(request: SpeakRequest, ctx: AuthContext | None = Depends(_require_auth)) -> Response:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="TTS requires OPENAI_API_KEY.")

    audio = await asyncio.to_thread(synthesize_speech, request.text, request.voice)
    if not audio:
        raise HTTPException(status_code=400, detail="Nothing to speak.")

    return Response(content=audio, media_type="audio/mpeg")


@router.post("/telephony/simulate")
async def telephony_simulate(request: VoiceSimulateRequest, ctx: AuthContext | None = Depends(_require_auth)) -> dict[str, Any]:
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
# WhatsApp / SMS Channel
# ---------------------------------------------------------------------------

@router.post("/messaging/inbound")
async def messaging_inbound(request: Request) -> dict:
    form = await request.form()
    return await whatsapp.handle_inbound_webhook(dict(form))


@router.post("/messaging/send")
async def messaging_send(ctx: AuthContext | None = Depends(_require_auth), to: str = "", body: str = "", channel: str = "whatsapp") -> dict:
    return await whatsapp.send_message(to, body, channel)


# ---------------------------------------------------------------------------
# Webhook Events API (for external systems to push events)
# ---------------------------------------------------------------------------

@router.post("/events")
async def receive_event(body: WebhookEventRequest) -> dict:
    logger.info("external_event_received", event_type=body.event_type)
    return {"status": "received", "event_type": body.event_type}


# ---------------------------------------------------------------------------
# Demo utilities
# ---------------------------------------------------------------------------

@router.post("/demo/reset")
async def reset_demo(ctx: AuthContext | None = Depends(_require_auth)) -> dict:
    """One-click demo reset — clears sessions, re-seeds KB, resets metrics."""
    if ctx and ctx.tenant_id != "demo-acme":
        raise HTTPException(status_code=403, detail="Demo reset only available for demo tenant")

    tenant_id = ctx.tenant_id if ctx else "demo-acme"

    from src.auth import seed_demo_data
    from src.database import get_connection

    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE tenant_id = ?)", (tenant_id,))
        conn.execute("DELETE FROM sessions WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM csat_surveys WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM audit_log WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM knowledge_articles WHERE tenant_id = ?", (tenant_id,))

    seed_demo_data()
    global _sessions
    _sessions = SessionManager(ttl_seconds=3600, max_sessions=1000)

    logger.info("demo_reset", tenant=tenant_id)
    return {"status": "demo_reset", "message": "Demo data has been reset. All sessions cleared, KB re-seeded."}


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------

@router.post("/integrations/webhooks")
async def register_webhook(request: Request, body: WebhookRegisterRequest) -> dict[str, str]:
    _require_settings_token(request)
    if body.event_type not in WEBHOOK_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unsupported event type: {body.event_type}")
    integration_router.register_webhook(body.event_type, body.url)
    return {"status": "registered", "event_type": body.event_type}


@router.delete("/integrations/webhooks/{event_type}")
async def delete_webhook(request: Request, event_type: str) -> dict[str, str]:
    _require_settings_token(request)
    if event_type not in WEBHOOK_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unsupported event type: {event_type}")
    integration_router.unregister_webhook(event_type)
    return {"status": "removed", "event_type": event_type}


@router.get("/integrations/status")
async def integrations_status() -> dict[str, Any]:
    settings = get_settings()
    vault = get_secrets_vault()
    creds = vault.credential_status(_env_credentials())
    hooks = vault.webhook_status()

    return {
        "encryption": {
            "enabled": vault.path.exists(),
            "vault_path": str(vault.path),
            "key_source": "env" if settings.integrations_encryption_key else "local_file",
        },
        "providers": {
            "openai": {
                "configured": creds["openai_api_key"]["configured"],
                "source": creds["openai_api_key"]["source"],
                "masked_key": creds["openai_api_key"]["masked"],
                "features": ["llm", "embeddings", "stt", "tts"],
            },
            "anthropic": {
                "configured": creds["anthropic_api_key"]["configured"],
                "source": creds["anthropic_api_key"]["source"],
                "masked_key": creds["anthropic_api_key"]["masked"],
                "features": ["llm"],
            },
            "gemini": {
                "configured": creds["gemini_api_key"]["configured"],
                "source": creds["gemini_api_key"]["source"],
                "masked_key": creds["gemini_api_key"]["masked"],
                "features": ["llm"],
            },
            "twilio": {
                "configured": all(
                    creds[key]["configured"]
                    for key in ("twilio_account_sid", "twilio_auth_token", "twilio_phone_number")
                ),
                "masked_sid": creds["twilio_account_sid"]["masked"],
                "masked_phone": creds["twilio_phone_number"]["masked"],
                "webhook_base_url": creds["twilio_webhook_base_url"]["masked"] or None,
                "source": "vault" if vault.get_credentials().get("twilio_account_sid") else (
                    "env" if _env_credentials().get("twilio_account_sid") else "none"
                ),
                "features": ["pstn", "voice_webhooks", "whatsapp", "sms"],
            },
            "hubspot": {
                "configured": creds["hubspot_api_key"]["configured"],
                "source": creds["hubspot_api_key"]["source"],
                "masked_key": creds["hubspot_api_key"]["masked"],
                "features": ["crm_lookup", "ticket_sync"],
            },
            "salesforce": {
                "configured": creds["salesforce_client_id"]["configured"],
                "source": creds["salesforce_client_id"]["source"],
                "masked_key": creds["salesforce_client_id"]["masked"],
                "features": ["crm_lookup", "case_management"],
            },
            "whatsapp": {
                "configured": all(
                    creds[key]["configured"]
                    for key in ("twilio_account_sid", "twilio_auth_token", "twilio_phone_number")
                ),
                "features": ["messaging", "inbound_webhook"],
            },
            "ipaas": {
                "configured": any(item["configured"] for item in hooks.values()),
                "webhook_signing": creds["webhook_signing_secret"]["configured"],
                "masked_signing_secret": creds["webhook_signing_secret"]["masked"],
                "events": hooks,
                "features": ["n8n", "zapier"],
            },
        },
        "mock_mode": not bool(settings.openai_api_key or settings.anthropic_api_key),
    }


@router.put("/integrations/credentials")
async def save_credentials(request: Request, body: CredentialsUpdateRequest) -> dict[str, Any]:
    _require_settings_token(request)
    vault = get_secrets_vault()
    updates = body.model_dump(exclude_unset=True)
    vault.set_credentials(updates)
    reload_settings()
    integration_router.load_from_vault()
    return {
        "status": "saved",
        "updated": list(updates.keys()),
        "providers": (await integrations_status())["providers"],
    }


@router.delete("/integrations/credentials/{credential_key}")
async def delete_credential(request: Request, credential_key: str) -> dict[str, str]:
    _require_settings_token(request)
    if credential_key not in CREDENTIAL_KEYS:
        raise HTTPException(status_code=400, detail=f"Unsupported credential: {credential_key}")
    get_secrets_vault().clear_credential(credential_key)
    reload_settings()
    integration_router.load_from_vault()
    return {"status": "cleared", "credential": credential_key}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

@router.post("/evaluation/run")
async def run_evaluation(ctx: AuthContext | None = Depends(_require_auth)) -> dict[str, Any]:
    from src.config import EVALUATION_DIR

    evaluator = AgentEvaluator(str(EVALUATION_DIR / "test_cases.json"))
    return await evaluator.run_suite()


# ---------------------------------------------------------------------------
# Agent & LLM config
# ---------------------------------------------------------------------------

@router.get("/agents")
async def list_agents() -> dict[str, Any]:
    from src.config import load_agent_config
    from src.llm.params import resolve_llm_params

    config = load_agent_config()
    defaults = config.get("llm_defaults", {})
    return {
        agent_id: {
            "name": cfg["name"],
            "channel": cfg["channel"],
            "tools": cfg.get("tools", []),
            "llm_params": resolve_llm_params(cfg, defaults),
        }
        for agent_id, cfg in config["agents"].items()
    }


@router.get("/llm/config")
async def get_llm_config() -> dict[str, Any]:
    from src.config import load_agent_config
    from src.llm.params import DEFAULT_LLM_PARAMS, resolve_llm_params

    config = load_agent_config()
    return {
        "defaults": DEFAULT_LLM_PARAMS,
        "global": config.get("llm_defaults", {}),
        "guardrails": config.get("guardrails", {}),
        "agents": {
            agent_id: resolve_llm_params(cfg, config.get("llm_defaults"))
            for agent_id, cfg in config["agents"].items()
        },
    }


# ---------------------------------------------------------------------------
# SSE streaming for voice
# ---------------------------------------------------------------------------

@router.get("/telephony/voice/stream")
async def voice_stream_sse(request: Request):
    """SSE endpoint for real-time voice transcription + response streaming.

    Accept `?speech=<text>` query param (simulated speech input) and streams
    back the agent response tokens one-by-one with grounding metrics.
    """
    from fastapi.responses import StreamingResponse

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
        result = await orchestrator.invoke(
            user_input=speech,
            customer_info="Caller via SSE stream",
        )

        response_text = result.get("response", "")
        tokens = response_text.split()

        for i, token in enumerate(tokens):
            if await request.is_disconnected():
                break
            chunk = token + (" " if i < len(tokens) - 1 else "")
            yield f"data: {json.dumps({'type': 'token', 'content': chunk, 'index': i, 'total': len(tokens)})}\n\n"
            await asyncio.sleep(0.03)

        done_payload = json.dumps({
            'type': 'done',
            'content': response_text,
            'agent_id': result.get('agent_id'),
            'tool_calls': result.get('tool_calls', []),
            'metrics': result.get('metrics', {}),
        })
        yield f"data: {done_payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


# ---------------------------------------------------------------------------
# KB version history + file upload
# ---------------------------------------------------------------------------

@router.get("/kb/articles/{article_id}/versions")
async def get_article_versions(article_id: int, ctx: AuthContext = Depends(require_auth)) -> dict:
    from src.database import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, content, tags, category, created_at, updated_at FROM knowledge_articles WHERE id = ? AND tenant_id = ?",
            (article_id, ctx.tenant_id),
        ).fetchall()
        return {"versions": [dict(r) for r in rows], "count": len(rows)}


@router.post("/kb/upload")
async def upload_kb_file(file: UploadFile = File(...), ctx: AuthContext = Depends(require_auth)) -> dict:
    """Upload a file and ingest it asynchronously into the knowledge base."""
    content = await file.read()
    text = content.decode("utf-8")
    task_id = await task_queue.enqueue("ingest_kb_file", {
        "content": text,
        "filename": file.filename or "upload.txt",
    })

    db.log_audit(ctx.tenant_id, ctx.user_id, "kb.file.uploaded", f"upload/{file.filename}", {
        "filename": file.filename, "size": len(text),
    })

    return {"status": "queued", "task_id": task_id, "filename": file.filename}


# ---------------------------------------------------------------------------
# Background task management
# ---------------------------------------------------------------------------

@router.post("/tasks/ingest")
async def task_ingest(source_path: str, ctx: AuthContext = Depends(require_auth)) -> dict:
    from pathlib import Path

    path = Path(source_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    task_id = await task_queue.enqueue("ingest_kb", {"path": str(path)})
    return {"status": "queued", "task_id": task_id, "source": source_path}


@router.post("/tasks/evaluate")
async def task_evaluate(ctx: AuthContext = Depends(require_auth)) -> dict:
    task_id = await task_queue.enqueue("run_evaluation", {})
    return {"status": "queued", "task_id": task_id}


@router.get("/tasks/{task_id}")
async def task_status(task_id: str) -> dict:
    result = task_queue.get_result(task_id)
    status = task_queue.get_status(task_id)
    return {"task_id": task_id, "status": status, "result": result}


# ---------------------------------------------------------------------------
# Enterprise integrations (Zendesk, ServiceNow, Slack)
# ---------------------------------------------------------------------------

@router.post("/integrations/zendesk/ticket")
async def zendesk_create_ticket(subject: str, description: str, requester_email: str = "") -> dict:
    client = ZendeskClient()
    return await client.create_ticket(subject, description, requester_email)


@router.post("/integrations/servicenow/incident")
async def servicenow_create_incident(short_description: str, description: str, caller_email: str = "") -> dict:
    client = ServiceNowClient()
    return await client.create_incident(short_description, description, caller_email)


@router.post("/integrations/slack/alert")
async def slack_send_alert(text: str, channel: str = "#general") -> dict:
    notifier = SlackNotifier()
    return await notifier.send_alert(channel, text)


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

@router.get("/observability/metrics")
async def observability_metrics() -> dict:
    return collector.snapshot()


@router.get("/observability/health")
async def observability_health() -> dict:
    snap = collector.snapshot()
    uptime = snap["uptime_seconds"]
    qsize = task_queue._queue.qsize() if task_queue._queue else 0
    return {
        "status": "healthy",
        "uptime_seconds": uptime,
        "requests_processed": snap["counters"].get("requests_total", 0),
        "errors": snap["counters"].get("errors_total", 0),
        "active_tasks": len(task_queue._active),
    "queued_tasks": qsize,
        }


# ---------------------------------------------------------------------------
# Continuous improvement / feedback loop
# ---------------------------------------------------------------------------

@router.get("/feedback/{agent_id}/report")
async def feedback_report(agent_id: str, tenant_id: str = "default") -> dict:
    engine = FeedbackEngine(tenant_id)
    return engine.get_feedback_report(agent_id)


@router.get("/feedback/{agent_id}/analyze")
async def feedback_analyze(agent_id: str, tenant_id: str = "default") -> dict:
    engine = FeedbackEngine(tenant_id)
    suggestions = engine.analyze(agent_id)
    return {"agent_id": agent_id, "suggestions": suggestions}


@router.post("/feedback/{agent_id}/snapshot")
async def feedback_snapshot(agent_id: str, hours: int = 24, tenant_id: str = "default") -> dict:
    engine = FeedbackEngine(tenant_id)
    return engine.record_snapshot(agent_id, hours)


@router.get("/feedback/{agent_id}/config")
async def feedback_get_config(agent_id: str, tenant_id: str = "default") -> dict:
    engine = FeedbackEngine(tenant_id)
    return engine.get_config(agent_id)


@router.put("/feedback/{agent_id}/config")
async def feedback_update_config(agent_id: str, body: dict, tenant_id: str = "default") -> dict:
    engine = FeedbackEngine(tenant_id)
    return engine.upsert_config(agent_id, **body)


@router.get("/feedback/{agent_id}/suggestions")
async def feedback_suggestions(agent_id: str, tenant_id: str = "default") -> dict:
    engine = FeedbackEngine(tenant_id)
    return {"suggestions": engine.get_suggestions(agent_id)}


@router.post("/feedback/suggestions/{suggestion_id}/apply")
async def feedback_apply_suggestion(suggestion_id: int, tenant_id: str = "default") -> dict:
    engine = FeedbackEngine(tenant_id)
    engine.mark_applied(suggestion_id)
    return {"status": "applied", "suggestion_id": suggestion_id}


@router.post("/feedback/{agent_id}/auto-adjust")
async def feedback_auto_adjust(agent_id: str, tenant_id: str = "default") -> dict:
    engine = FeedbackEngine(tenant_id)
    adjustments = engine.apply_auto_adjustment(agent_id)
    return {"agent_id": agent_id, "adjustments": adjustments or "none_needed"}
