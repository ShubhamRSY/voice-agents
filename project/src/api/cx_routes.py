"""CX platform routes: agent inbox, handoff, tickets, NPS, email, translation, workflows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from structlog import get_logger

from src.analytics import analytics
from src.database import db
from src.integrations.email_channel import email_channel
from src.integrations.meta_messaging import meta_messenger
from src.integrations.translation import detect_locale, translate_text
from src.api.deps import CSATRequest, integration_router, require_auth

logger = get_logger()
router = APIRouter()


class HandoffRequest(BaseModel):
    reason: str = Field(min_length=1)
    priority: str = "normal"


class InboxReplyRequest(BaseModel):
    message: str = Field(min_length=1)


class TicketCreateRequest(BaseModel):
    subject: str = Field(min_length=1)
    description: str = ""
    session_id: str = ""
    customer_id: str = ""
    priority: str = "normal"
    assigned_to: str = ""


class TicketUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None
    description: str | None = None
    subject: str | None = None


class NPSRequest(BaseModel):
    session_id: str
    score: int = Field(ge=0, le=10)
    feedback: str = ""


class EmailSendRequest(BaseModel):
    to: str = Field(min_length=3)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    session_id: str = ""


class EmailInboundRequest(BaseModel):
    from_addr: str = Field(alias="from", default="")
    to: str = ""
    subject: str = ""
    text: str = ""
    body: str = ""
    session_id: str = ""

    model_config = {"populate_by_name": True}


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1)
    target_locale: str = "en"
    source_locale: str | None = None


class WorkflowRequest(BaseModel):
    name: str = Field(min_length=1)
    trigger_event: str = Field(min_length=1)
    conditions: dict = Field(default_factory=dict)
    actions: list = Field(default_factory=list)
    id: int | None = None


class MessageFeedbackRequest(BaseModel):
    session_id: str
    rating: int = Field(description="1 = thumbs up, -1 = thumbs down")


@router.get("/inbox")
async def list_inbox(status: str | None = None, ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    items = db.list_inbox(tenant_id, status=status)
    return {"inbox": items, "count": len(items)}


@router.post("/inbox/{session_id}/claim")
async def claim_conversation(session_id: str, ctx: Any = Depends(require_auth)) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if ctx and session["tenant_id"] != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    updated = db.assign_session(session_id, ctx.user_id if ctx else "agent")
    db.log_audit(session["tenant_id"], ctx.user_id if ctx else None, "inbox.claim", "session", {"session_id": session_id})
    return {"status": "claimed", "session": updated}


@router.post("/inbox/{session_id}/reply")
async def agent_reply(session_id: str, body: InboxReplyRequest, ctx: Any = Depends(require_auth)) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if ctx and session["tenant_id"] != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    msg_id = db.save_agent_message(session_id, ctx.user_id if ctx else "agent", body.message)
    return {"status": "sent", "message_id": msg_id}


@router.post("/inbox/{session_id}/resolve")
async def resolve_conversation(session_id: str, ctx: Any = Depends(require_auth)) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if ctx and session["tenant_id"] != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    updated = db.resolve_handoff(session_id)
    await integration_router.on_conversation_end(session_id, "resolved_by_agent", {})
    return {"status": "resolved", "session": updated}


@router.post("/handoff/{session_id}")
async def escalate_session(session_id: str, body: HandoffRequest, ctx: Any = Depends(require_auth)) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if ctx and session["tenant_id"] != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    updated = db.escalate_session(session_id, body.reason, body.priority)
    await integration_router.on_escalation(session_id, body.reason)
    return {"status": "queued", "session": updated}


@router.get("/tickets")
async def list_tickets(status: str | None = None, ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    return {"tickets": db.list_tickets(tenant_id, status=status)}


@router.post("/tickets")
async def create_ticket(body: TicketCreateRequest, ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    ticket = db.create_ticket(
        tenant_id, body.subject, body.description,
        session_id=body.session_id, customer_id=body.customer_id,
        priority=body.priority, assigned_to=body.assigned_to,
    )
    await integration_router.on_ticket_created(ticket)
    return {"status": "created", "ticket": ticket}


@router.patch("/tickets/{ticket_id}")
async def update_ticket(ticket_id: int, body: TicketUpdateRequest, ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    updated = db.update_ticket(ticket_id, tenant_id, **body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"status": "updated", "ticket": updated}


@router.post("/nps")
async def submit_nps(body: NPSRequest) -> dict:
    session = db.get_session(body.session_id)
    tenant_id = session["tenant_id"] if session else "default"
    result = db.save_nps(body.session_id, tenant_id, body.score, body.feedback)
    logger.info("nps_submitted", session_id=body.session_id, score=body.score)
    return {"status": "recorded", "nps": result}


@router.get("/nps/stats")
async def nps_stats(ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    return {"stats": db.get_nps_stats(tenant_id)}


@router.post("/csat")
async def submit_csat_cx(body: CSATRequest) -> dict:
    session = db.get_session(body.session_id)
    tenant_id = session["tenant_id"] if session else "default"
    try:
        result = db.save_csat(body.session_id, tenant_id, body.score, body.feedback)
    except Exception as exc:
        logger.warning("csat_save_failed", session_id=body.session_id, error=str(exc))
        result = {"id": 0, "session_id": body.session_id, "score": body.score}
    logger.info("csat_submitted", session_id=body.session_id, score=body.score)
    return {"status": "recorded", "csat": result}


@router.get("/cx/dashboard")
async def cx_dashboard(hours: int = 168, ctx: Any = Depends(require_auth)) -> dict:
    try:
        tenant_id = ctx.tenant_id if ctx else "default"
        conv = db.get_conversation_analytics(tenant_id, hours=hours)
        csat = db.get_csat_stats(tenant_id)
        nps = db.get_nps_stats(tenant_id)
        handoff = db.get_handoff_stats(tenant_id, hours=hours)
        agent_stats = analytics.get_agent_scorecard(tenant_id, hours=hours)
        timeline = analytics.get_conversation_timeline(tenant_id, hours=hours)
        avg_response_ms = db.get_avg_response_time_ms(tenant_id, hours=hours)
        message_feedback = db.get_message_feedback_stats(tenant_id)
        return {
            "conversations": {**conv, "avg_response_time_ms": avg_response_ms},
            "csat": csat,
            "nps": nps,
            "handoff": handoff,
            "agents": agent_stats,
            "timeline": timeline,
            "message_feedback": message_feedback,
            "period_hours": hours,
        }
    except Exception as e:
        logger.error("cx_dashboard_error", error=str(e))
        return {"conversations": {}, "csat": {}, "nps": {}, "handoff": {}, "agents": [], "timeline": [], "message_feedback": {}, "period_hours": hours}


@router.post("/messages/{message_id}/feedback")
async def message_feedback(message_id: int, body: MessageFeedbackRequest, ctx: Any = Depends(require_auth)) -> dict:
    if body.rating not in (-1, 1):
        raise HTTPException(status_code=400, detail="rating must be 1 or -1")
    tenant_id = ctx.tenant_id if ctx else "default"
    result = db.save_message_feedback(message_id, body.session_id, tenant_id, body.rating)
    return {"status": "recorded", "feedback": result}


@router.post("/email/send")
async def send_email(body: EmailSendRequest, ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    return await email_channel.send_email(body.to, body.subject, body.body, body.session_id, tenant_id)


@router.post("/email/inbound")
async def email_inbound(body: EmailInboundRequest, ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    payload = body.model_dump(by_alias=True)
    return await email_channel.handle_inbound(payload, tenant_id)


@router.post("/translate")
async def translate(body: TranslateRequest, ctx: Any = Depends(require_auth)) -> dict:
    result = await translate_text(body.text, body.target_locale, body.source_locale)
    if not body.source_locale:
        result["detected_locale"] = detect_locale(body.text)
    return result


@router.get("/workflows")
async def list_workflows(ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    return {"workflows": db.list_workflows(tenant_id)}


@router.post("/workflows")
async def save_workflow(body: WorkflowRequest, ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    wf = db.save_workflow(tenant_id, body.name, body.trigger_event, body.conditions, body.actions, body.id)
    return {"status": "saved", "workflow": wf}


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int, ctx: Any = Depends(require_auth)) -> dict:
    tenant_id = ctx.tenant_id if ctx else "default"
    if not db.delete_workflow(workflow_id, tenant_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"status": "deleted"}


@router.get("/meta/webhook")
async def meta_webhook_verify(
    hub_mode: str = "",
    hub_verify_token: str = "",
    hub_challenge: str = "",
) -> int:
    from src.config import get_settings
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/meta/webhook")
async def meta_webhook_inbound(request: Request) -> dict:
    from src.config import get_settings
    import json

    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if settings.meta_app_secret and not meta_messenger.verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    payload = json.loads(body)
    return await meta_messenger.handle_webhook(payload)
