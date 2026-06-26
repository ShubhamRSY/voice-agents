"""Enterprise Voice & Chat AI Agent Platform — entry point with WebSocket, middleware."""

import asyncio
import time
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.auth_routes import router as auth_router
from src.api.chat_routes import router as chat_router
from src.api.kb_routes import router as kb_router
from src.api.telephony_routes import router as telephony_router
from src.api.integration_routes import router as integration_router_mod
from src.api.ops_routes import router as ops_router
from src.api.deps import integration_router
from src.auth import seed_demo_data
from src.config import ROOT_DIR, get_settings, reload_settings
from src.database import init_db
from src.integrations.secrets_vault import get_secrets_vault
from src.logging_config import setup_logging
from src.middleware import RateLimitMiddleware, TenantMiddleware
from src.tasks import task_queue
from src.observability import active_gauge, setup_sentry, setup_opentelemetry
from src.workflows.orchestrator import AgentOrchestrator

STATIC_DIR = ROOT_DIR / "static"

logger = structlog.get_logger()


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
    logger.info("shutting_down")


app = FastAPI(
    title="Nexus · Enterprise Voice & Chat AI Agents",
    description="Production-grade omnichannel AI agent platform with multi-tenant auth, streaming, analytics, and enterprise integrations.",
    version="2.0.0",
    lifespan=lifespan,
)

settings = get_settings()

# Middleware stack
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantMiddleware)
app.add_middleware(RateLimitMiddleware, rpm=settings.rate_limit_rpm)


@app.middleware("http")
async def track_active_requests(request, call_next):
    active_gauge.incr_requests()
    try:
        response = await call_next(request)
    finally:
        active_gauge.decr_requests()
    return response


# Domain routers — all under /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(kb_router, prefix="/api/v1")
app.include_router(telephony_router, prefix="/api/v1")
app.include_router(integration_router_mod, prefix="/api/v1")
app.include_router(ops_router, prefix="/api/v1")

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
            final_result = None

            async for event in orchestrator.invoke_stream(
                user_input=message,
                customer_info=data.get("customer_info", "No customer identified"),
            ):
                if event["type"] == "token":
                    await websocket.send_json({
                        "type": "token",
                        "content": event["content"],
                    })
                elif event["type"] == "done":
                    final_result = event

            if final_result:
                await websocket.send_json({
                    "type": "done",
                    "content": final_result.get("response", ""),
                    "agent_id": final_result.get("agent_id"),
                    "tool_calls": final_result.get("tool_calls", []),
                    "metrics": final_result.get("metrics", {}),
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
        except Exception as close_err:
            logger.debug("websocket_send_failed", error=str(close_err))
    finally:
        try:
            await websocket.close()
        except Exception as close_err:
            logger.debug("websocket_close_failed", error=str(close_err))


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
    )
