"""FastAPI routes for chat, voice, copilot, RAG, and evaluation."""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.evaluation.evaluator import AgentEvaluator
from src.integrations.webhooks import IntegrationRouter
from src.rag.ingestion import ingest_directory, ingest_file
from src.rag.vector_store import VectorStore
from src.telephony.call_router import CallMetadata, CallRouter, RoutingRule
from src.telephony.twilio_handler import TwilioVoiceHandler
from src.telephony.twiml_parser import parse_twiml
from src.workflows.orchestrator import AgentOrchestrator

logger = structlog.get_logger()
router = APIRouter()
integration_router = IntegrationRouter()
voice_handler = TwilioVoiceHandler()


class ChatRequest(BaseModel):
    message: str
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


class VoiceSimulateRequest(BaseModel):
    call_sid: str = "SIM-CALL-001"
    from_number: str = "+15551234567"
    speech: str | None = None
    sip_headers: dict[str, str] = Field(default_factory=dict)


_call_router = CallRouter()
_call_router.add_rule(RoutingRule("vip", "from:+1555", "+15559999999", priority=10))
_call_router.set_fallback("+15551111111")


_sessions: dict[str, AgentOrchestrator] = {}


def _get_session(session_id: str, agent_id: str) -> AgentOrchestrator:
    if session_id not in _sessions:
        _sessions[session_id] = AgentOrchestrator(agent_id)
    return _sessions[session_id]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "enterprise-voice-agents"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or "default"
    orchestrator = _get_session(session_id, request.agent_id)

    result = await orchestrator.invoke(
        user_input=request.message,
        customer_info=request.customer_info or "No customer identified",
    )

    await integration_router.on_conversation_start(session_id, "chat", {
        "agent_id": request.agent_id,
    })

    return ChatResponse(
        response=result["response"],
        agent_id=result["agent_id"],
        tool_calls=result.get("tool_calls", []),
        metrics=result.get("metrics", {}),
    )


@router.post("/copilot")
async def copilot(request: CopilotRequest) -> dict[str, Any]:
    orchestrator = AgentOrchestrator(request.agent_id)
    result = await orchestrator.invoke(
        user_input=request.message,
        extra_context=request.conversation_summary,
    )
    return result


@router.delete("/chat/{session_id}")
async def end_session(session_id: str) -> dict[str, str]:
    _sessions.pop(session_id, None)
    await integration_router.on_conversation_end(session_id, "completed", {})
    return {"status": "session_ended"}


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


@router.post("/telephony/voice/inbound")
async def voice_inbound(request: Request):
    return await voice_handler.handle_inbound(request)


@router.post("/telephony/voice/process")
async def voice_process(request: Request):
    return await voice_handler.handle_inbound(request)


@router.post("/telephony/voice/status")
async def voice_status(request: Request) -> dict[str, Any]:
    return await voice_handler.handle_status_callback(request)


@router.post("/telephony/simulate")
async def telephony_simulate(request: VoiceSimulateRequest) -> dict[str, Any]:
    """Simulate PSTN/CCaaS voice call flow without Twilio credentials."""
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


@router.post("/integrations/webhooks")
async def register_webhook(request: WebhookRegisterRequest) -> dict[str, str]:
    integration_router.register_webhook(request.event_type, request.url)
    return {"status": "registered", "event_type": request.event_type}


@router.post("/evaluation/run")
async def run_evaluation() -> dict[str, Any]:
    evaluator = AgentEvaluator("tests/evaluation/test_cases.json")
    return await evaluator.run_suite()


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
    """Return user-configurable LLM parameters per agent."""
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
