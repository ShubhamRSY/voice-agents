<div align="center">

# Nexus

**Open-source omnichannel AI agent platform for contact centers.**  
One orchestrator routing chat, copilot, and voice conversations — with RAG, multi-LLM support, SSE streaming, and WebSocket streaming.

[![CI](https://github.com/ShubhamRSY/voice-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/ShubhamRSY/voice-agents/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-109%20unit%20passing-brightgreen.svg)](tests/)

</div>

---

## Table of Contents

- [What Is Nexus?](#what-is-nexus)
- [Recent Changes](#recent-changes)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Production Deployment](#production-deployment)
- [Architecture](#architecture)
- [Features](#features)
- [API Overview](#api-overview)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

---

## What Is Nexus?

Customer support teams lose context switching between channels — chat, phone, email, and internal tools each live in separate silos. Nexus solves this with a single AI-powered orchestrator that handles every conversation from one runtime, with one knowledge base, and one feedback loop to improve responses over time.

**Three channels, one engine:**

| Channel | Purpose |
|---------|---------|
| **Chat** | Live AI conversation with SSE streaming, WebSocket streaming, RAG citations, full session history |
| **Copilot** | Agent-assist — paste a transcript, get an AI-suggested reply |
| **Voice** | PSTN calls via Twilio, Amazon Connect, or any SIP/CCaaS. Live STT, AI TTS. |

> **No API key required.** Without `OPENAI_API_KEY`, Nexus falls back to a mock LLM — the console, voice simulator, smoke tests, and all 109+ unit tests work immediately.

---

## Recent Changes

### v2.0.0 — Production Hardening (June 2026)

| Change | Description |
|--------|-------------|
| **HTTPS/TLS** | Caddy reverse proxy with auto-HTTPS (Let's Encrypt), security headers, edge rate limiting |
| **PostgreSQL + Redis** | Docker Compose with Postgres 16 (connection pooling), Redis 7, health checks, persistent volumes |
| **Rate limiting** | Redis-backed sliding window with in-memory fallback, per-endpoint-group limits |
| **CI with PostgreSQL** | CI runs tests against both SQLite and PostgreSQL; conditional LLM E2E tests |
| **Zero-downtime deploys** | Gunicorn with preload, max-requests, graceful SIGHUP reload, config file |
| **Structured logging** | File sink with rotation, Loki push support, JSON output for production |
| **Secrets management** | HashiCorp Vault integration (optional, via `hvac`), layered credential resolution |
| **Automated backups** | Backup script for PostgreSQL + ChromaDB with S3 upload, retention, cron scheduling |
| **Load testing config** | 15 benchmark scenarios, concurrency profiles, performance budgets in `benchmarks.json` |
| **Dependencies pinned** | All 28 runtime deps pinned to exact versions; ruff + mypy in dev group |
| **Dockerfile optimized** | Multi-stage build -> gunicorn config, COPY safety, non-root user |
| **109+ tests** | Full coverage: unit, integration, E2E, non-functional, security, concurrency |

---

## Prerequisites

- **Python 3.11+**
- **pip** (bundled with Python)
- **git**
- *(Optional)* An [OpenAI](https://platform.openai.com/api-keys), [Anthropic](https://console.anthropic.com/), or [Google Gemini](https://ai.google.dev/) API key for production LLM access
- *(Optional)* [Docker](https://www.docker.com/) + [Docker Compose](https://docs.docker.com/compose/) for containerized deployment

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/ShubhamRSY/voice-agents.git
cd voice-agents

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install with dev dependencies
pip install -e ".[dev]"

# 4. Copy the environment template (no edits needed to start)
cp config/environment/.env.example config/environment/.env

# 5. Start the server
uvicorn src.main:app --reload --port 8001
```

Open **[http://127.0.0.1:8001](http://127.0.0.1:8001)** — the Nexus console loads with a welcome screen, session sidebar, and channel selector.

**Smoke test the API:**

```bash
# Non-streaming chat
curl -s -X POST http://127.0.0.1:8001/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How do I reset my password?","session_id":"demo-1"}' | jq

# SSE streaming chat
curl -s http://127.0.0.1:8001/api/v1/chat/sse?message=Hello

# WebSocket streaming (via wscat)
wscat -c ws://127.0.0.1:8001/api/v1/chat/stream
```

---

## Production Deployment

### Docker Compose (recommended)

```bash
# Full stack with TLS, Postgres, Redis
docker compose -f deploy/docker/docker-compose.yml up

# Include automated backups
docker compose -f deploy/docker/docker-compose.yml --profile backup up
```

This starts:
- **Caddy** — TLS termination, rate limiting, security headers, JSON access logs
- **PostgreSQL 16** — persistent volume, health checks, auto-extensions
- **Redis 7** — persistent volume, caching + task queue
- **Nexus** — gunicorn with 2-4x CPU workers, max-requests, graceful reload
- **Backup** (profile) — daily PostgreSQL + ChromaDB backup to local or S3

### Environment Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DOMAIN` | No | `:80` | Domain for auto-HTTPS (set to `nexus.example.com` in prod) |
| `DATABASE_URL` | No | SQLite | `postgresql://user:pass@host:5432/db` |
| `REDIS_URL` | No | in-memory | `redis://host:6379/0` |
| `OPENAI_API_KEY` | No | mock | LLM provider key |
| `SENTRY_DSN` | No | — | Error tracking |
| `OTEL_ENDPOINT` | No | — | OpenTelemetry collector |
| `VAULT_ADDR` | No | — | HashiCorp Vault URL |
| `CORS_ORIGINS` | No | `*` | Set to your domain in production |
| `BACKUP_S3_BUCKET` | No | — | S3 bucket for offsite backups |

Full reference: [`config/environment/.env.example`](config/environment/.env.example)

### Bare Metal

```bash
# Install production dependencies
pip install -e "."

# Set environment variables (see .env.example)
export DATABASE_URL=postgresql://...
export REDIS_URL=redis://...

# Start with gunicorn (zero-downtime)
gunicorn src.main:app --config deploy/docker/gunicorn.conf.py

# Graceful reload (zero-downtime)
kill -HUP <gunicorn-pid>
```

---

## Architecture

```
                          ┌─────────────┐
                          │   Caddy     │  ← TLS termination, rate limiting
                          │  (reverse   │
                          │   proxy)    │
                          └──────┬──────┘
                                 │
                          ┌──────▼──────┐
                          │   FastAPI   │  ← Auth, CORS, tenant, rate limit middleware
                          │   (Nexus)   │
                          └──┬───┬───┬──┘
                             │   │   │
              ┌──────────────┤   │   ├──────────────┐
              │              │   │   │              │
       ┌──────▼──────┐ ┌────▼───▼───▼────┐ ┌───────▼──────┐
       │   Chat      │ │   Orchestrator  │ │   Voice      │
       │   Copilot   │ │  (LangGraph)    │ │  (Twilio)    │
       │   SSE/WS    │ │  RAG + Guardrails│ │  STT/TTS     │
       └──────┬──────┘ └────┬───┬───┬────┘ └──────┬───────┘
              │             │   │   │              │
              └─────────────┘   │   └──────────────┘
                                │
                    ┌───────────┼───────────┐
                    │           │           │
              ┌─────▼────┐ ┌───▼───┐ ┌─────▼────┐
              │ Postgres │ │ Redis │ │ ChromaDB │
              │ (SQLite  │ │(cache+│ │ (vector  │
              │   dev)   │ │queue) │ │  store)  │
              └──────────┘ └───────┘ └──────────┘
```

Nexus follows a layered design: domain routers handle channel-specific logic, the orchestrator manages session state and prompt construction, services provide RAG and feedback, and a provider layer abstracts over OpenAI, Anthropic, and Gemini models.

Full architecture → [docs/overview.md](docs/overview.md#architecture).

---

## Features

- **Omnichannel** — unified console for chat, copilot, and voice with per-mode message filtering and sync toggle
- **Multi-LLM** — OpenAI GPT-4o, Anthropic Claude 3.5, Google Gemini 2.0 — switch per agent
- **Live streaming** — SSE (`GET /api/v1/chat/sse`) and WebSocket (`ws://.../chat/stream`) deliver tokens word-by-word
- **RAG citations** — vector-based retrieval augments every response with source-grounded knowledge
- **Voice (PSTN)** — Twilio, Amazon Connect, generic SIP/CCaaS with STT/TTS pipeline
- **Feedback engine** — CSAT ratings dynamically tune agent temperature and RAG thresholds
- **Encrypted vault** — AES-256-GCM for API keys and integration credentials at rest
- **Session management** — history sidebar, rename, new/clear session
- **iPaaS webhooks** — lifecycle events for n8n/Zapier
- **Dark mode UI** — polished frontend with animations, typing indicator, streaming cursor
- **Production infrastructure** — TLS termination, PostgreSQL, Redis, Sentry, OpenTelemetry, structured logging, automated backups

---

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register a new tenant + admin user |
| POST | `/api/v1/auth/login` | Login, receive JWT |
| GET | `/api/v1/auth/me` | Current user info |
| POST | `/api/v1/chat` | Send message, get AI response |
| GET | `/api/v1/chat/sse` | SSE streaming chat (token-by-token) |
| WS | `/api/v1/chat/stream` | WebSocket streaming chat |
| POST | `/api/v1/copilot` | Agent-assist: transcript → suggested reply |
| DELETE | `/api/v1/chat/{session_id}` | End a session |
| GET | `/api/v1/sessions/stats` | Active session count |
| GET | `/api/v1/sessions/{id}/history` | Session message history |
| POST | `/api/v1/csat` | Submit CSAT rating |
| GET | `/api/v1/csat/stats` | CSAT statistics |
| GET | `/api/v1/agents` | List configured agents |
| GET | `/api/v1/llm/config` | LLM configuration overview |
| GET | `/api/v1/health` | Health check (no auth) |
| GET | `/api/v1/metrics` | Prometheus metrics |
| GET | `/api/v1/observability/health` | Detailed observability status |
| GET | `/api/v1/analytics/dashboard` | Conversation analytics dashboard |
| POST | `/api/v1/evaluation/run` | Run agent evaluation suite |
| POST | `/api/v1/demo/reset` | Reset demo data |
| POST | `/api/v1/events` | Receive external events |

Full reference at `/docs` when the server is running.

---

## Testing

```bash
# Unit & integration tests (109 tests)
pytest tests/ --ignore=tests/e2e --timeout=60 -v

# E2E tests (requires running server)
python -m uvicorn src.main:app --port 8001 &
pytest tests/e2e/ -v --reruns 2

# Full CI pipeline locally
bash scripts/ci.sh

# Lint + type check
ruff check src/ scripts/
mypy src/
```

---

## Contributing

1. Fork the repo and create a branch from `main`
2. Run tests locally with `pytest tests/`
3. Lint with `ruff check src/ scripts/`
4. Run type check with `mypy src/`
5. Submit a pull request

All contributions — features, bug fixes, docs, tests — are welcome.

---

## License

[MIT](LICENSE) © [Shubham RSY](https://github.com/ShubhamRSY)
