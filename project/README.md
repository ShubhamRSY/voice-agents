<div align="center">

# Nexus

**Purpose-built AI agents. One CX platform. (Open-source)**  
Nexus is an omnichannel AI agent platform for customer experience teams — one orchestrator for **Chat**, **Copilot**, and **Voice**, grounded with **RAG**, protected by **JWT auth + guardrails**, and built for **operations** (streaming, rate limits, logs, backups).

[![CI](https://github.com/ShubhamRSY/voice-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/ShubhamRSY/voice-agents/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPLv3](https://img.shields.io/badge/License-AGPLv3-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-109%20unit%20passing-brightgreen.svg)](tests/)

</div>

---

## Table of Contents

- [What Is Nexus?](#what-is-nexus)
- [Nexus Concepts](#nexus-concepts)
- [Recent Changes](#recent-changes)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Production Deployment](#production-deployment)
- [Architecture](#architecture)
- [Features](#features)
- [API Overview](#api-overview)
- [Testing](#testing)
- [Contributing](#contributing)
- [Keeping `main` Safe](#keeping-main-safe)
- [License](#license)

---

## What Is Nexus?

Customer experience (CX) teams lose time and accuracy when chat, voice, and internal tooling live in separate silos. Nexus solves this with a single AI-powered runtime that can resolve interactions, assist frontline agents, and improve operations — all from one console and one orchestration engine.

**Three channels, one engine:**

| Channel | Purpose |
|---------|---------|
| **Chat** | Live AI conversation with SSE streaming, WebSocket streaming, RAG citations, full session history |
| **Copilot** | Agent-assist — paste a transcript, get an AI-suggested reply |
| **Voice** | PSTN calls via Twilio, Amazon Connect, or any SIP/CCaaS. Live STT, AI TTS. |

> **No API key required.** Without `OPENAI_API_KEY`, Nexus falls back to a mock LLM — the console, voice simulator, smoke tests, and all 109+ unit tests work immediately.

**What we do (and how it transforms CX)**

- **AI Agents for Customers**: resolve customer inquiries end-to-end across chat and voice — from intake and authentication to execution and follow-up.
- **AI Agents for Frontline Teams (Copilot)**: guide interactions in real time with the right context, next-best actions, and draft responses that reduce handle time and errors.
- **AI Agents for Operations**: evaluate interactions, surface insights, and enable continuous improvement (quality + safety) across both human and AI agents.

**AI-driven outcomes**

- **Faster, better resolutions**: always-on support with consistent answers grounded in your knowledge base.
- **Speed + accuracy + consistency**: reduce errors and handle time with copilot assistance and guardrails.
- **Operate CX with full visibility**: health, logs, analytics, and (optional) observability integrations to continuously improve performance.

---

## Commercial / Hosted Nexus (coming soon)

Nexus is open-source, but a hosted/enterprise offering is planned for teams that want managed operations and advanced CX workflows.

**Licensing**

- **Open-source**: AGPLv3 (`project/LICENSE`)
- **Commercial license**: available for closed-source/proprietary usage — see [`COMMERCIAL_LICENSE.md`](COMMERCIAL_LICENSE.md)

**Planned hosted features**

- **Managed deployments** (updates, backups, monitoring, alerts)
- **SSO / enterprise auth** (SAML/OIDC) + user provisioning
- **Advanced analytics & QA** (evaluation dashboards, coaching insights, quality scoring)
- **Premium integrations** (CRM/ticketing/telephony connectors) and reliability tooling

**Branding**

- The **Nexus** name/logo/branding are trademarks. See [`TRADEMARKS.md`](TRADEMARKS.md).

If you want early access, open a GitHub issue with “Hosted Nexus” in the title.

---

## Nexus Concepts

Nexus is organized around a small set of primitives so you can reason about the system (and extend it safely) without needing to learn every file at once.

**Core primitives**

- **Orchestrator**: The brain of the runtime. It receives a user event (chat message, copilot transcript, or voice turn), loads session context, retrieves relevant knowledge, selects an agent policy, and streams back tokens.
- **Agents**: Configured behaviors (prompts + tools + routing rules). An agent can be specialized (billing, refunds, troubleshooting) or general-purpose, and can be swapped per request.
- **Channels**: Transport + UX mode. Channel adapters normalize inputs/outputs so the orchestrator sees a consistent event shape while each channel keeps its own streaming protocol and pacing.
  - **Chat**: JSON response or streaming via SSE/WS
  - **Copilot**: transcript → suggested reply (agent-assist)
  - **Voice**: streaming STT → LLM → TTS (telephony provider integration)
- **Knowledge base (RAG)**: A document store + embeddings + retrieval step that grounds responses in your internal docs. Nexus attaches citations so answers can be audited.
- **Guardrails**: Safety and reliability layers around generation: rate limits, auth, tool allowlists, prompt constraints, and (optionally) secrets resolution via Vault.
- **State & storage**: Session history and metadata stored in SQLite (dev) or Postgres (prod), with Redis used for caching and queueing.

**What “Nexus” means in practice**

- **One runtime for all channels**: you do not maintain separate “chat bot” and “voice bot” codepaths with divergent prompt logic.
- **Consistent observability**: streaming, errors, and latency can be traced per session across channels.
- **Safe extension points**: most customization should happen by adding/adjusting agents, tools, and KB content rather than editing request plumbing.

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

# Optional: enable demo users and sample KB for local exploration
# echo "DEMO_MODE=true" >> config/environment/.env

# 5. Start the server
uvicorn src.main:app --reload --port 8001
```

Open **[http://127.0.0.1:8001](http://127.0.0.1:8001)** — the Nexus console loads with a welcome screen, session sidebar, and channel selector.

If you deployed to a VM, open your production console URL (example): **[https://yournexus.duckdns.org/](https://yournexus.duckdns.org/)**.

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

**Free hosting ($0/month):** See [docs/deploy-oracle-duckdns.md](docs/deploy-oracle-duckdns.md) for Oracle Cloud + DuckDNS step-by-step.

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
| `APP_ENV` | No | `development` | Set to `production` to disable docs and demo reset |
| `AUTH_REQUIRED` | No | `false` | Set to `true` in production |
| `DEMO_MODE` | No | `false` | Set to `true` for local demo users/KB |
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

### Enterprise operations (runbooks)

| Milestone | Docs |
|-----------|------|
| M1 — SSO + observability | [OIDC Auth0 setup](docs/ops-oidc-auth0.md) · [Monitoring & alerts](docs/ops-monitoring.md) |
| M2 — DR + load testing | [DR runbook (RPO/RTO)](docs/ops-dr-runbook.md) · [Load testing](docs/ops-load-testing.md) |
| M3 — SOC 2 readiness | [SOC 2 checklist](docs/soc2-readiness.md) · [Access controls](docs/soc2/access-controls.md) · [Key rotation](docs/soc2/key-rotation.md) |
| M4 — HA / multi-region | [HA architecture](docs/ha-multi-region.md) |

Scripts: `scripts/restore-drill.sh` · `scripts/loadtest/k6-smoke.js` · `scripts/setup-backup-timer.sh`

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

## Keeping `main` Safe

If you’re collaborating (or deploying from this repo), these practices help prevent accidental breakage and secret leaks.

**Branch protection (recommended)**

- Protect `main` and require PRs (no direct pushes).
- Require status checks to pass (CI / tests / lint / typecheck).
- Require at least 1 review approval (2 for risky areas like auth, billing, deployments).
- Enable “Require branches to be up to date before merging”.
- Prefer “Squash and merge” to keep history readable.

**CI as the gate**

- Keep `scripts/ci.sh` (or the CI workflow) as the single source of truth for what must pass before merge.
- Add new checks there first (then mark them required in branch protection).

**Secrets hygiene**

- Never commit `.env` files. Use `config/environment/.env.example` as the source of truth.
- Treat production credentials as external (Vault, secret manager, or CI secrets) — not repo files.
- If you suspect a key leaked: revoke/rotate immediately, then purge from git history (do not rely on “delete the file”).

**Safer local development**

- Use the mock LLM by default (no `OPENAI_API_KEY`) when iterating on routing and UI.
- Develop features behind config flags when possible, so `main` remains deployable.

---

## License

[MIT](LICENSE) © [Shubham RSY](https://github.com/ShubhamRSY)
