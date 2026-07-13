"""Enterprise Voice & Chat AI Agent Platform — entry point with WebSocket, middleware."""

# Must run before chromadb (and any other sqlite3 consumers).
import src.sqlite_compat  # noqa: F401

import asyncio
import time
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from src.api.auth_routes import router as auth_router
from src.api.oidc_routes import router as oidc_router
from src.api.chat_routes import router as chat_router
from src.api.kb_routes import router as kb_router
from src.api.telephony_routes import router as telephony_router
from src.api.integration_routes import router as integration_router_mod
from src.api.admin_routes import router as admin_router
from src.api.ops_routes import router as ops_router
from src.api.cx_routes import router as cx_router
from src.api.enterprise_routes import router as enterprise_router
from src.api.portal_routes import router as portal_router
from src.api.saas_routes import router as saas_router
from src.api.deps import integration_router
from src.auth import decode_jwt, seed_demo_data
from src import __version__
from src.config import ROOT_DIR, get_cors_origins_list, get_settings, reload_settings
from src.database import init_db
from src.integrations.secrets_vault import get_secrets_vault
from src.logging_config import setup_logging
from src.middleware import MetricsMiddleware, RateLimitMiddleware, TenantMiddleware
from src.tasks import task_queue
from src.observability import setup_sentry, setup_opentelemetry
from src.workflows.orchestrator import AgentOrchestrator

STATIC_DIR = ROOT_DIR / "static"
_CACHEABLE_STATIC_SUFFIXES = (".css", ".js", ".webp", ".png", ".jpg", ".jpeg", ".svg", ".woff2", ".woff")
# Marketing assets change often — do not pin immutable long cache on these paths.
_MARKETING_STATIC_PREFIXES = (
    "landing.",
    "brand-logos.",
    "nexus-logo.",
    "contact.",
    "pricing.",
    "faq.",
    "integrations.",
)


class CachedStaticFiles(StaticFiles):
    """Serve static assets; long cache for hashed assets, short cache for marketing."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code != 200 or scope.get("method") != "GET":
            return response
        if path.endswith(_CACHEABLE_STATIC_SUFFIXES):
            if any(path.startswith(p) for p in _MARKETING_STATIC_PREFIXES):
                response.headers["Cache-Control"] = "public, max-age=300, must-revalidate"
            else:
                response.headers["Cache-Control"] = "public, max-age=604800, immutable"
        return response


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
        vault=get_secrets_vault().diagnostics(),
        demo_mode=settings.demo_mode,
        auth_required=settings.auth_required,
        app_env=settings.app_env,
        background_queue=True,
        sentry=bool(settings.sentry_dsn),
        otel=bool(settings.otel_endpoint),
    )
    yield
    await task_queue.stop()
    logger.info("shutting_down")


settings = get_settings()
_docs_enabled = not settings.is_production

app = FastAPI(
    title="Nexus · Enterprise Voice & Chat AI Agents",
    description="Production-grade omnichannel AI agent platform with multi-tenant auth, streaming, analytics, and enterprise integrations.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# Middleware stack
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins_list(settings),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantMiddleware)
app.add_middleware(RateLimitMiddleware, rpm=settings.rate_limit_rpm)
app.add_middleware(MetricsMiddleware)


# Domain routers — all under /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(oidc_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(kb_router, prefix="/api/v1")
app.include_router(telephony_router, prefix="/api/v1")
app.include_router(integration_router_mod, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(ops_router, prefix="/api/v1")
app.include_router(cx_router, prefix="/api/v1")
app.include_router(enterprise_router, prefix="/api/v1")
app.include_router(portal_router, prefix="/api/v1")
app.include_router(saas_router, prefix="/api/v1")

if STATIC_DIR.exists():
    app.mount("/static", CachedStaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# WebSocket streaming endpoint
# ---------------------------------------------------------------------------

def _extract_ws_token(websocket: WebSocket) -> str | None:
    token = websocket.query_params.get("token")
    if token:
        return token
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


async def _authorize_websocket(websocket: WebSocket) -> bool:
    settings = get_settings()
    if not settings.auth_required:
        return True

    token = _extract_ws_token(websocket)
    if not token or decode_jwt(token) is None:
        await websocket.close(code=4401, reason="Authentication required")
        return False
    return True


@app.websocket("/api/v1/chat/stream")
async def chat_stream(websocket: WebSocket):
    if not await _authorize_websocket(websocket):
        return

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

@app.get("/signup")
async def signup_ui():
    page = STATIC_DIR / "signup.html"
    if page.exists():
        return FileResponse(page, headers={"Cache-Control": "no-cache, must-revalidate"})
    return {"message": "Signup page not found", "api": "/api/v1/saas/signup"}


@app.get("/pricing")
async def pricing_ui():
    page = STATIC_DIR / "pricing.html"
    if page.exists():
        return FileResponse(page, headers={"Cache-Control": "no-cache, must-revalidate"})
    raise HTTPException(status_code=404, detail="Pricing page not found")


@app.get("/faq")
async def faq_ui():
    page = STATIC_DIR / "faq.html"
    if page.exists():
        return FileResponse(page, headers={"Cache-Control": "no-cache, must-revalidate"})
    raise HTTPException(status_code=404, detail="FAQ not found")


@app.get("/contact")
async def contact_ui():
    page = STATIC_DIR / "contact.html"
    if page.exists():
        return FileResponse(page, headers={"Cache-Control": "no-cache, must-revalidate"})
    raise HTTPException(status_code=404, detail="Contact page not found")


@app.get("/integrations")
async def integrations_ui():
    page = STATIC_DIR / "integrations.html"
    if page.exists():
        return FileResponse(page, headers={"Cache-Control": "no-cache, must-revalidate"})
    return {"message": "Integrations page not found", "api": "/api/v1/integrations/catalog"}


@app.get("/legal/terms")
async def legal_terms():
    page = STATIC_DIR / "legal" / "terms.html"
    if page.exists():
        return FileResponse(page, headers={"Cache-Control": "no-cache, must-revalidate"})
    raise HTTPException(status_code=404, detail="Terms not found")


@app.get("/legal/privacy")
async def legal_privacy():
    page = STATIC_DIR / "legal" / "privacy.html"
    if page.exists():
        return FileResponse(page, headers={"Cache-Control": "no-cache, must-revalidate"})
    raise HTTPException(status_code=404, detail="Privacy policy not found")


@app.get("/legal/licensing")
async def legal_licensing():
    page = STATIC_DIR / "legal" / "licensing.html"
    if page.exists():
        return FileResponse(page, headers={"Cache-Control": "no-cache, must-revalidate"})
    return {"message": "See COMMERCIAL_LICENSE.md", "startup": "$12,000/year", "growth": "$36,000/year", "enterprise": "from $96,000/year"}


@app.get("/portal")
async def portal_ui():
    portal = STATIC_DIR / "portal.html"
    if portal.exists():
        return FileResponse(portal, headers={"Cache-Control": "no-cache, must-revalidate"})
    return {"message": "Portal not found", "api": "/api/v1/portal"}


@app.get("/landing")
async def landing_ui():
    landing = STATIC_DIR / "landing.html"
    if landing.exists():
        return FileResponse(landing, headers={"Cache-Control": "no-cache, must-revalidate"})
    return {"message": "Landing page not found"}


@app.get("/")
async def ui():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache, must-revalidate"})
    return {"message": "UI not found. Use /docs for API."}


@app.get("/api/v1")
async def api_root():
    settings = get_settings()
    return {
        "service": "Nexus Enterprise AI Agents",
        "version": __version__,
        "docs": "/docs" if not settings.is_production else None,
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.app_host,
        port=settings.app_port,
    )
