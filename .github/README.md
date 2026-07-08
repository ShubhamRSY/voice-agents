<div align="center">

# Nexus

**Purpose-built AI agents. One CX platform. (Open-source)**  
Nexus is an omnichannel AI agent platform for customer experience teams — one orchestrator for **Chat**, **Copilot**, and **Voice**, grounded with **RAG**, protected by **JWT auth + guardrails**, and built for **operations** (streaming, rate limits, logs, backups).

[![CI](https://github.com/ShubhamRSY/voice-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/ShubhamRSY/voice-agents/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPLv3](https://img.shields.io/badge/License-AGPLv3-blue.svg)](project/LICENSE)
[![Tests](https://img.shields.io/badge/tests-109%20unit%20passing-brightgreen.svg)](project/tests/)

</div>

**Live pilot:** [https://yournexus.duckdns.org/](https://yournexus.duckdns.org/) — chat, copilot, voice, RAG, JWT auth, and Auth0 OIDC SSO.

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
- **Commercial license**: available for closed-source/proprietary usage — see [`project/COMMERCIAL_LICENSE.md`](project/COMMERCIAL_LICENSE.md)

**Planned hosted features** (beyond what’s already in the open-source repo)

- **Fully managed operations** (hands-off updates, on-call, SLA)
- **Advanced analytics & QA** (evaluation dashboards, coaching insights, quality scoring)
- **Premium integrations** (CRM/ticketing/telephony connectors) and white-glove onboarding

**Already in open source (pilot-ready)**

- OIDC SSO (Auth0 / Okta / Azure AD / Google Workspace) + JIT user provisioning
- Request metrics, latency tracking, auth-failure counters (`/api/v1/metrics`)
- Daily backups, restore drill, DR runbooks, k6 load-test harness
- SOC 2 readiness checklist and access-control / key-rotation docs

**Branding**

- The **Nexus** name/logo/branding are trademarks. See [`project/TRADEMARKS.md`](project/TRADEMARKS.md).

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

### v2.1.0 — Enterprise pilot (July 2026)

| Change | Description |
|--------|-------------|
| **Live production** | Deployed at [yournexus.duckdns.org](https://yournexus.duckdns.org/) (Oracle Cloud VM + Caddy + systemd) |
| **OIDC SSO** | Auth0 integration with JIT provisioning, role mapping, audit logging — [setup guide](project/docs/ops-oidc-auth0.md) |
| **Observability** | Request/latency/5xx/auth metrics middleware; Prometheus + JSON health dashboards |
| **Reliability** | Daily backup timer, restore-drill script, RPO/RTO runbook |
| **SOC 2 prep** | Evidence checklist, access-control policy template, key-rotation procedures |
| **Load testing** | k6 smoke script with performance budgets |
| **HA roadmap** | Multi-region / Postgres HA architecture doc for future scale |

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
- *(Optional)* An OpenAI / Anthropic / Gemini API key for production LLM access
- *(Optional)* Docker + Docker Compose for containerized deployment

---

## Quick Start

```bash
git clone https://github.com/ShubhamRSY/voice-agents.git
cd voice-agents/project
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config/environment/.env.example config/environment/.env
uvicorn src.main:app --reload --port 8001
```

Open **[http://127.0.0.1:8001](http://127.0.0.1:8001)** — the Nexus console loads with a welcome screen, session sidebar, and channel selector.

**Live pilot:** [https://yournexus.duckdns.org/](https://yournexus.duckdns.org/)

### Production readiness (pilot)

| Area | Status |
|------|--------|
| Core product (chat, copilot, voice, RAG) | Ready |
| Auth (JWT + Auth0 OIDC SSO) | Ready |
| Backups, DR, uptime monitoring | Ready |
| SOC 2 formal audit / HA multi-region | Future — see `project/docs/` |

---

## Production Deployment

### Docker Compose (recommended)

```bash
cd voice-agents/project

# Full stack with TLS, Postgres, Redis
docker compose -f deploy/docker/docker-compose.yml up

# Include automated backups
docker compose -f deploy/docker/docker-compose.yml --profile backup up
```

**Free hosting ($0/month):** Oracle Cloud + DuckDNS guide: [`project/docs/deploy-oracle-duckdns.md`](project/docs/deploy-oracle-duckdns.md)

---

## Architecture

```text
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

Nexus follows a layered design: channel routers handle chat/copilot/voice inputs, the orchestrator manages session state and prompt construction, and services provide RAG + integrations behind guardrails.

Deeper architecture doc: [`project/docs/overview.md`](project/docs/overview.md#architecture)

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
- **Production infrastructure** — TLS termination, PostgreSQL, Redis, structured logging, automated backups

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
| GET | `/api/v1/health` | Health check (no auth) |

Full reference at `/docs` when the server is running.

---

## Testing

```bash
cd voice-agents/project

# Unit & integration tests
pytest tests/ --ignore=tests/e2e --timeout=60 -v

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

**Branch protection (recommended)**

- Protect `main` and require PRs (no direct pushes).
- Require status checks to pass (CI / tests / lint / typecheck).
- Require at least 1 review approval.
- Enable “Require branches to be up to date before merging”.

**Secrets hygiene**

- Never commit `.env` files. Use `project/config/environment/.env.example` as the source of truth.
- Treat production credentials as external (Vault, secret manager, or CI secrets) — not repo files.

---

## License

[MIT](project/LICENSE) © [Shubham RSY](https://github.com/ShubhamRSY)

