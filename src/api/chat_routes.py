"""Chat, copilot, session management, CSAT, and streaming routes."""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from structlog import get_logger

from src.config import load_agent_config
from src.database import db
from src.workflows.orchestrator import AgentOrchestrator
from src.api.deps import (
    ChatRequest, ChatResponse, CopilotRequest, CSATRequest,
    _sessions, integration_router, require_auth, get_session,
)

logger = get_logger()
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, ctx: Any = Depends(require_auth)) -> ChatResponse:
    agent_config = load_agent_config()
    if request.agent_id not in agent_config.get("agents", {}):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown agent: {request.agent_id}")

    tenant_id = ctx.tenant_id if ctx else "default"
    session_id = request.session_id or f"session-{uuid.uuid4().hex[:12]}"
    orchestrator = get_session(session_id, request.agent_id, tenant_id)

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


@router.post("/copilot")
async def copilot(request: CopilotRequest, ctx: Any = Depends(require_auth)) -> dict[str, Any]:
    orchestrator = AgentOrchestrator(request.agent_id)
    result = await orchestrator.invoke(
        user_input=request.message,
        extra_context=request.conversation_summary,
    )
    return result


@router.get("/chat/sse")
async def chat_stream_sse(
    session_id: str = "",
    agent_id: str = "chat_support",
    message: str = "",
    customer_info: str = "",
    ctx: Any = Depends(require_auth),
) -> StreamingResponse:
    """Server-Sent Events streaming endpoint for chat responses."""
    agent_config = load_agent_config()
    if agent_id not in agent_config.get("agents", {}):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_id}")

    tenant_id = ctx.tenant_id if ctx else "default"
    sid = session_id or f"session-{uuid.uuid4().hex[:12]}"

    async def event_stream():
        orchestrator = get_session(sid, agent_id, tenant_id)
        collected: list[str] = []
        async for event in orchestrator.invoke_stream(
            user_input=message,
            customer_info=customer_info or "No customer identified",
        ):
            if event["type"] == "token":
                collected.append(event["content"])
                yield f"data: {json.dumps({'type': 'token', 'content': event['content']})}\n\n"
            elif event["type"] == "done":
                db.create_session(sid, tenant_id, agent_id, "chat", customer_info)
                db.save_message(sid, "user", message)
                db.save_message(
                    sid, "assistant", event.get("response", ""),
                    tool_calls=event.get("tool_calls", []),
                    metrics=event.get("metrics", {}),
                )
                yield f"data: {json.dumps({'type': 'done', 'content': event.get('response', ''), 'agent_id': event.get('agent_id'), 'tool_calls': event.get('tool_calls', []), 'metrics': event.get('metrics', {})})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
async def csat_stats(ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    return {"stats": db.get_csat_stats(tenant_id)}
