"""Operational routes: health, metrics, observability, feedback, analytics, evaluation, demo, agents, tasks, events, LLM config."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from structlog import get_logger

from src.auth import AuthContext, require_auth
from src.config import get_settings
from src.database import db, get_connection
from src.analytics import analytics
from src.evaluation.evaluator import AgentEvaluator
from src.feedback.engine import FeedbackEngine
from src.observability import active_gauge, collector
from src.tasks import task_queue
from src.api.deps import (
    WebhookEventRequest, require_auth as require_auth_dep,
    _sessions,
)

logger = get_logger()
router = APIRouter()


# ---------------------------------------------------------------------------
# Health & Metrics (consolidated — single /api/v1/metrics for Prometheus)
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict[str, Any]:
    from src.integrations.secrets_vault import get_secrets_vault

    settings = get_settings()
    vault = get_secrets_vault().diagnostics()
    if settings.openai_api_key:
        rag_mode = "openai"
    else:
        # Avoid loading sentence-transformers on every health probe.
        rag_mode = "local_embeddings"
    degraded = not vault["operational"]
    return {
        "status": "degraded" if degraded else "healthy",
        "service": "enterprise-voice-agents",
        "stt_available": bool(settings.openai_api_key),
        "tts_available": bool(settings.openai_api_key),
        "tts_voice": "shimmer",
        "rag_mode": rag_mode,
        "vault": vault,
        "saas_signup_enabled": settings.saas_signup_enabled,
    }


@router.get("/metrics")
async def metrics_prometheus() -> Any:
    from fastapi.responses import Response
    active_gauge.set_sessions(_sessions.active_count)
    content = collector.prometheus_text() + "\n" + active_gauge.prometheus_text()
    return Response(content=content, media_type="text/plain; charset=utf-8")


@router.get("/observability/health")
async def observability_health() -> dict:
    snap = collector.snapshot()
    uptime = snap["uptime_seconds"]
    gauge = active_gauge.snapshot()
    latency = snap["histograms"].get("request_latency_ms", {})
    counters = snap["counters"]
    return {
        "status": "healthy",
        "uptime_seconds": uptime,
        "requests_processed": counters.get("requests_total", 0),
        "errors": counters.get("errors_total", 0),
        "http_5xx": counters.get("http_5xx_total", 0),
        "http_4xx": counters.get("http_4xx_total", 0),
        "auth_failures": counters.get("auth_failures_total", 0),
        "oidc_failures": counters.get("oidc_failures_total", 0),
        "latency_ms": latency,
        "active_requests": gauge["active_requests"],
        "active_tasks": gauge["active_tasks"],
        "active_sessions": gauge["active_sessions"],
        "peak_requests": gauge["peak_requests"],
        "queued_tasks": task_queue._backend.queue_size if task_queue._backend else 0,
        "sentry_enabled": bool(get_settings().sentry_dsn),
        "otel_enabled": bool(get_settings().otel_endpoint),
    }


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.get("/analytics/dashboard")
async def analytics_dashboard(hours: int = 24, ctx: AuthContext = Depends(require_auth)) -> dict:
    try:
        return {"dashboard": analytics.get_dashboard(ctx.tenant_id, hours)}
    except Exception as e:
        logger.error("analytics_dashboard_error", error=str(e))
        return {"dashboard": {"conversations": {}, "csat": {}, "active_sessions": 0, "recent_activity": [], "period_hours": hours}}


@router.get("/analytics/agents")
async def analytics_agents(hours: int = 168, ctx: AuthContext = Depends(require_auth)) -> dict:
    try:
        return {"scorecard": analytics.get_agent_scorecard(ctx.tenant_id, hours)}
    except Exception as e:
        logger.error("analytics_agents_error", error=str(e))
        return {"scorecard": []}


@router.get("/analytics/timeline")
async def analytics_timeline(hours: int = 24, ctx: AuthContext = Depends(require_auth)) -> dict:
    try:
        return {"timeline": analytics.get_conversation_timeline(ctx.tenant_id, hours)}
    except Exception as e:
        logger.error("analytics_timeline_error", error=str(e))
        return {"timeline": []}


@router.get("/analytics/audit-log")
async def audit_log(limit: int = 100, ctx: AuthContext = Depends(require_auth)) -> dict:
    try:
        return {"logs": db.get_audit_logs(ctx.tenant_id, limit)}
    except Exception as e:
        logger.error("audit_log_error", error=str(e))
        return {"logs": []}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

@router.post("/evaluation/run")
async def run_evaluation(ctx: Any = Depends(require_auth_dep)) -> dict[str, Any]:
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
# Background tasks
# ---------------------------------------------------------------------------

@router.post("/tasks/ingest")
async def task_ingest(source_path: str, ctx: AuthContext = Depends(require_auth)) -> dict:
    from pathlib import Path

    path = Path(source_path)
    if not path.exists():
        from fastapi import HTTPException
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
# Feedback / continuous improvement
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


# ---------------------------------------------------------------------------
# External events
# ---------------------------------------------------------------------------

@router.post("/events")
async def receive_event(body: WebhookEventRequest) -> dict:
    logger.info("external_event_received", event_type=body.event_type)
    return {"status": "received", "event_type": body.event_type}


# ---------------------------------------------------------------------------
# Demo utilities
# ---------------------------------------------------------------------------

@router.post("/demo/reset")
async def reset_demo(ctx: Any = Depends(require_auth_dep)) -> dict:
    settings = get_settings()
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not found")

    from src.auth import seed_demo_data

    tenant_id = ctx.tenant_id if ctx else "demo-acme"

    if ctx and ctx.tenant_id != "demo-acme":
        raise HTTPException(status_code=403, detail="Demo reset only available for demo tenant")

    with get_connection() as conn:
        conn.execute("DELETE FROM csat_surveys WHERE session_id IN (SELECT id FROM sessions WHERE tenant_id = ?)", (tenant_id,))
        conn.execute("DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE tenant_id = ?)", (tenant_id,))
        conn.execute("DELETE FROM sessions WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM audit_log WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM kb_versions WHERE article_id IN (SELECT id FROM knowledge_articles WHERE tenant_id = ?)", (tenant_id,))
        conn.execute("DELETE FROM knowledge_articles WHERE tenant_id = ?", (tenant_id,))

    seed_demo_data()
    import src.api.deps as deps
    deps._sessions = deps.SessionManager(ttl_seconds=3600, max_sessions=1000)

    logger.info("demo_reset", tenant=tenant_id)
    return {"status": "demo_reset", "message": "Demo data has been reset. All sessions cleared, KB re-seeded."}
