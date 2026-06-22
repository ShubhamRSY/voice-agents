"""Enterprise Voice & Chat AI Agent Platform — entry point with WebSocket, metrics, middleware."""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import integration_router, router
from src.auth import seed_demo_data
from src.config import ROOT_DIR, get_settings, reload_settings
from src.database import init_db
from src.integrations.secrets_vault import get_secrets_vault
from src.logging_config import setup_logging
from src.middleware import RateLimitMiddleware, TenantMiddleware
from src.workflows.orchestrator import AgentOrchestrator
from src.tasks import task_queue
from src.observability import setup_sentry, setup_opentelemetry, collector

STATIC_DIR = ROOT_DIR / "static"

logger = structlog.get_logger()

# In-memory metrics
METRICS: dict[str, Any] = {
    "requests_total": 0,
    "chat_requests": 0,
    "voice_requests": 0,
    "copilot_requests": 0,
    "errors_total": 0,
    "avg_response_time_ms": 0,
    "response_times": [],
    "started_at": time.time(),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    setup_sentry()
    setup_opentelemetry()
    settings = reload_settings()
    init_db()
    seed_demo_data()
    integration_router.load_from_vault()
    await task_queue.start()
    logger.info(
        "starting_platform",
        host=settings.app_host,
        port=settings.app_port,
        openai_configured=bool(settings.openai_api_key),
        vault_enabled=get_secrets_vault().path.exists(),
        demo_data_seeded=True,
        background_queue=True,
        sentry=bool(settings.sentry_dsn),
        otel=bool(settings.otel_endpoint),
    )
    yield
    await task_queue.stop()
    logger.info("shutting_down", uptime_seconds=round(time.time() - METRICS["started_at"]))


app = FastAPI(
    title="Nexus · Enterprise Voice & Chat AI Agents",
    description="Production-grade omnichannel AI agent platform with multi-tenant auth, streaming, analytics, and enterprise integrations.",
    version="2.0.0",
    lifespan=lifespan,
)

# Middleware stack
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantMiddleware)
app.add_middleware(RateLimitMiddleware, rpm=60)

app.include_router(router, prefix="/api/v1")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# WebSocket streaming endpoint
# ---------------------------------------------------------------------------

@app.websocket("/api/v1/chat/stream")
async def chat_stream(websocket: WebSocket):
    await websocket.accept()
    session_id = "default"
    agent_id = "chat_support"

    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        session_id = data.get("session_id", f"ws-{int(time.time())}")
        agent_id = data.get("agent_id", "chat_support")
        message = data.get("message", "")

        if message:
            orchestrator = AgentOrchestrator(agent_id)
            result = await orchestrator.invoke(
                user_input=message,
                customer_info=data.get("customer_info", "No customer identified"),
            )

            response_text = result.get("response", "")
            tokens = response_text.split()

            for i, token in enumerate(tokens):
                chunk = token + (" " if i < len(tokens) - 1 else "")
                await websocket.send_json({
                    "type": "token",
                    "content": chunk,
                    "index": i,
                    "total": len(tokens),
                })
                await asyncio.sleep(0.02)

            await websocket.send_json({
                "type": "done",
                "content": response_text,
                "agent_id": result.get("agent_id"),
                "tool_calls": result.get("tool_calls", []),
                "metrics": result.get("metrics", {}),
            })
        else:
            await websocket.send_json({"type": "error", "content": "Empty message"})

    except asyncio.TimeoutError:
        await websocket.send_json({"type": "error", "content": "No message received within 10s"})
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", session_id=session_id)
    except Exception as exc:
        logger.error("websocket_error", error=str(exc))
        try:
            await websocket.send_json({"type": "error", "content": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Prometheus metrics endpoint
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def prometheus_metrics():
    uptime = time.time() - METRICS["started_at"]
    avg_rt = METRICS["avg_response_time_ms"]

    lines = [
        "# HELP nexus_requests_total Total requests processed",
        "# TYPE nexus_requests_total counter",
        f'nexus_requests_total{{service="nexus"}} {METRICS["requests_total"]}',
        f'nexus_chat_requests{{service="nexus"}} {METRICS["chat_requests"]}',
        f'nexus_voice_requests{{service="nexus"}} {METRICS["voice_requests"]}',
        f'nexus_copilot_requests{{service="nexus"}} {METRICS["copilot_requests"]}',
        f'nexus_errors_total{{service="nexus"}} {METRICS["errors_total"]}',
        "# HELP nexus_avg_response_time_ms Average response time in ms",
        "# TYPE nexus_avg_response_time_ms gauge",
        f'nexus_avg_response_time_ms{{service="nexus"}} {avg_rt}',
        "# HELP nexus_uptime_seconds Service uptime",
        "# TYPE nexus_uptime_seconds gauge",
        f'nexus_uptime_seconds{{service="nexus"}} {uptime:.0f}',
        "# HELP nexus_active_sessions Current active sessions",
        "# TYPE nexus_active_sessions gauge",
        f'nexus_active_sessions{{service="nexus"}} 0',
    ]
    return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


# ---------------------------------------------------------------------------
# UI and root
# ---------------------------------------------------------------------------

@app.get("/")
async def ui():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache, must-revalidate"})
    return {"message": "UI not found. Use /docs for API."}


@app.get("/api/v1")
async def api_root():
    return {
        "service": "Nexus Enterprise AI Agents",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
