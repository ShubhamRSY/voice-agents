"""Enterprise Voice & Chat AI Agent Platform — entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router
from src.config import ROOT_DIR, get_settings, reload_settings
from src.logging_config import setup_logging

STATIC_DIR = ROOT_DIR / "static"

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = reload_settings()
    logger.info(
        "starting_platform",
        host=settings.app_host,
        port=settings.app_port,
        openai_configured=bool(settings.openai_api_key),
    )
    yield
    logger.info("shutting_down")


app = FastAPI(
    title="Enterprise Voice & Chat AI Agents",
    description="Production-ready platform for voice, chat, and copilot AI agents with RAG, telephony, and CRM integrations.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def ui():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "UI not found. Use /docs for API."}


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
