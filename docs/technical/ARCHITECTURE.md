# Nexus — Enterprise AI Agent Platform

**Technical Architecture Document**  
Version 2.0 | June 2026

---

## 1. Executive Summary

Nexus is a production-grade, omnichannel AI agent platform purpose-built for contact centers and customer-support automation. It deploys and operates AI agents across chat, voice (PSTN/CCaaS), and agent-assist copilot channels — all backed by a unified orchestration core, retrieval-augmented generation (RAG) pipeline, and enterprise integration layer.

The platform ships as a single FastAPI application with a built-in web console, REST API, offline mock mode for development and CI, and Docker-based deployment. It is designed for platform engineers, contact center operators, and developers who need a configurable, observable, and regression-tested AI agent runtime.

---

## 2. System Overview

### 2.1 Design Principles

| Principle | Description |
|---|---|
| **Omnichannel** | Single orchestrator serves chat, voice, and copilot with channel-specific prompts |
| **Configuration-driven** | Agent behavior, LLM parameters, and routing defined in YAML — no code changes required |
| **Grounded responses** | RAG retrieval precedes generation; every response carries grounding metrics |
| **Graceful degradation** | Mock LLM + keyword search when API keys or vector scores are unavailable |
| **Observable** | Structured logging, per-request metrics, automated evaluation for regression control |
| **Multi-tenant** | Tenant isolation at the middleware and database query level |

### 2.2 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Customer & Agent Channels                      │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ Web      │  │ PSTN/CCaaS   │  │ REST API Clients         │   │
│  │ Console  │  │ Twilio · AWS │  │ CCaaS · CRM · Custom     │   │
│  │ Chat/Cop │  │ Connect · SIP│  │ Apps                     │   │
│  └────┬─────┘  └──────┬───────┘  └───────────┬──────────────┘   │
└───────┼───────────────┼───────────────────────┼──────────────────┘
        │               │                       │
┌───────▼───────────────▼───────────────────────▼──────────────────┐
│                      API Gateway (FastAPI)                        │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Middleware Stack: CORS → Tenant Isolation → Rate Limit  │    │
│  ├──────────────────────────────────────────────────────────┤    │
│  │  Routes: Chat · Voice · Copilot · RAG · KB · Analytics  │    │
│  │          Evaluation · Feedback · Integrations · Auth     │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│                    Agent Runtime                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Orchestrator (LangGraph ReAct Loop)                     │    │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌────────────┐  │    │
│  │  │ Prompt   │ │ Guardrails│ │Grounding│ │ Tool       │  │    │
│  │  │ Templates│ │ Injection │ │Scoring  │ │ Executor   │  │    │
│  │  └──────────┘ │ Blocking  │ └─────────┘ └────────────┘  │    │
│  │               └──────────┘                               │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│              Tools, Integrations & Knowledge                      │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ CRM     │ │Telephony │ │ iPaaS    │ │ Vector   │ │ Secrets│ │
│  │ HubSpot │ │ Twilio   │ │ Webhooks │ │ Store    │ │ Vault  │ │
│  │Salesforce│ │AWS Connect│ │ n8n/Zap │ │ChromaDB  │ │Fernet  │ │
│  └─────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 API Gateway (`src/main.py` + `src/api/routes.py`)

FastAPI application with ~60 REST endpoints across 15 resource domains. Middleware stack provides cross-origin support, multi-tenant isolation, and rate limiting (60 rpm default). WebSocket endpoint enables token-by-token streaming for real-time chat UX.

### 3.2 Agent Runtime (`src/workflows/orchestrator.py`)

The `AgentOrchestrator` is the central invocation pipeline. It implements a LangGraph ReAct loop that:

1. Receives user input with session context and customer metadata
2. Applies guardrails (prompt injection detection, output sanitization)
3. Retrieves relevant context from the RAG pipeline (semantic + keyword)
4. Executes the LLM ReAct loop with channel-specific prompt templates
5. Invokes tools (CRM lookup, ticket creation, KB search, human transfer)
6. Scores the response for grounding and hallucination risk
7. Returns structured response with metrics

### 3.3 RAG Pipeline (`src/rag/`)

Two-stage retrieval system:

- **Semantic retrieval:** ChromaDB vector store with OpenAI embeddings (or local deterministic embeddings in mock mode)
- **Keyword fallback:** TF-IDF style search when vector scores fall below threshold (0.7)

Documents are ingested via CLI script (`scripts/ingest_kb.py`) or REST API, chunked at 512 tokens with 64-token overlap.

### 3.4 Agent Configuration (`config/agents.yaml`)

Four pre-configured agents:

| Agent | Channel | LLM | Temperature | Tools |
|---|---|---|---|---|
| `voice_support` | Voice (Twilio, AWS Connect) | GPT-4o-mini | 0.3 | lookup, search, ticket, transfer |
| `chat_support` | Web Chat | GPT-4o-mini | 0.4 | lookup, search, ticket, update_crm, transfer |
| `copilot` | Agent Assist | GPT-4o-mini | 0.2 | search, draft, summarize |
| `whatsapp_support` | WhatsApp | GPT-4o-mini | 0.35 | lookup, search, ticket |

All LLM parameters (temperature, top_p, top_k, stop sequences, chain-of-thought, few-shot) are configurable per agent without code changes.

### 3.5 Guardrails & Safety (`src/llm/guardrails.py`)

- Prompt injection detection using regex patterns
- Output sanitization to prevent system prompt leakage
- Hallucination scoring via grounding overlap analysis
- Configurable threshold (default 0.15)

### 3.6 Telephony Layer (`src/telephony/`)

Abstract CCaaS adapter pattern supporting multiple providers:

- **Twilio:** TwiML-based voice handling with speech gather, DTMF, and call routing
- **Amazon Connect:** Lambda-style JSON webhook integration with contact flow attributes
- **Generic SIP/CCaaS:** Extensible base class (`CcaasVoiceHandler`) for custom providers

Common call routing features:
- Skill-based routing with priority rules
- VIP detection by caller ID prefix
- SIP `X-*` header extraction and routing
- Round-robin and fallback destinations

### 3.7 Feedback Loop (`src/feedback/engine.py`)

Continuous improvement engine that:

- Records periodic performance snapshots (containment rate, CSAT, latency, hallucination rate)
- Compares against configurable targets per agent
- Generates actionable improvement suggestions
- Auto-adjusts LLM parameters (temperature, max_tokens) when metrics drift
- Emits webhook events for external workflow integration

### 3.8 Enterprise Integrations (`src/integrations/`)

| Integration | Type | Purpose |
|---|---|---|
| HubSpot | CRM | Contact lookup, ticket management |
| Salesforce | CRM | Alternative CRM adapter |
| Zendesk | Ticketing | Ticket CRUD operations |
| ServiceNow | ITSM | Incident and request management |
| Slack | Notification | Alerts, escalation notifications |
| WhatsApp | Messaging | Twilio-based SMS/WhatsApp channel |
| n8n / Zapier | iPaaS | Outbound webhook lifecycle events |
| Secrets Vault | Security | Fernet-encrypted credential storage |

---

## 4. Data Model

### 4.1 SQLite Schema (Primary Store)

```
tenants         → users → sessions → messages
                            ↓
              knowledge_articles → kb_versions
              csat_surveys
              audit_log
              feedback_loop_config
              agent_performance_trends
              improvement_suggestions
```

### 4.2 Vector Store (ChromaDB)

Persistent ChromaDB instance stores document embeddings for semantic search. Supports S3 backup via boto3.

### 4.3 Encrypted Vault

Fernet (AES-128) encrypted JSON file (`data/integrations.vault`) stores API keys and webhook URLs. Vault values override environment variables when both are set.

---

## 5. API Reference

All endpoints prefixed with `/api/v1`. Full OpenAPI documentation available at `/docs` at runtime.

| Domain | Methods | Purpose |
|---|---|---|
| Auth | `POST /auth/login`, `/register`, `GET /me` | JWT-based authentication |
| Chat | `POST /chat`, `WS /chat/stream`, `DELETE /chat/{id}` | Conversational AI |
| Copilot | `POST /copilot` | Agent assist response drafting |
| Voice | `POST /telephony/voice/*`, `/simulate` | PSTN call handling |
| RAG | `POST /rag/ingest`, `/rag/search` | Knowledge retrieval |
| KB | CRUD `/kb/articles` | Knowledge base management |
| Evaluation | `POST /evaluation/run` | Automated quality testing |
| Feedback | `GET /feedback/{agent_id}/*` | Performance analytics |
| Integrations | Webhook CRUD, credential management | External system wiring |
| Analytics | `GET /analytics/*` | Dashboard metrics |
| CSAT | `POST /csat`, `GET /csat/stats` | Customer satisfaction |
| Tasks | `POST /tasks/*`, `GET /tasks/{id}` | Background job queue |
| Observability | `GET /metrics`, `/observability/*` | Monitoring and health |

---

## 6. Deployment

### 6.1 Docker

```dockerfile
FROM python:3.11-slim
EXPOSE 8000
HEALTHCHECK --interval=30s --start-period=15s --retries=3 \
  CMD curl -sf http://localhost:8000/api/v1/health
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.2 CI/CD Pipeline (GitHub Actions)

| Stage | Environment | Commands |
|---|---|---|
| Lint | ubuntu-latest | `ruff check`, `mypy` |
| Unit Tests | Python 3.11, 3.12 | `pytest` (ignoring e2e) |
| E2E Tests | Python 3.11 | Live server + `pytest tests/e2e/` |
| Docker | ubuntu-latest | Build + smoke test (main only) |

### 6.3 Environment Requirements

- Python ≥ 3.11
- SQLite 3 (embedded)
- ChromaDB (embedded, persistent)
- No external services required for development/mock mode

---

## 7. Security

- **Authentication:** JWT-based with configurable enforcement (`auth_required` flag)
- **Multi-tenancy:** Tenant isolation via middleware and parameterized queries
- **Credential storage:** Fernet (AES-128) encrypted vault at rest
- **API key masking:** All credential responses show only masked values
- **Webhook signing:** HMAC-SHA256 signatures on outbound webhooks
- **Rate limiting:** 60 requests per minute per tenant (configurable)
- **Input sanitization:** Prompt injection guardrails and output filtering

---

## 8. Testing Strategy

| Category | Scope | Tools |
|---|---|---|
| Unit | Agent logic, guardrails, routing, tools | pytest, pytest-asyncio |
| Integration | API endpoints, database, telephony handlers | FastAPI TestClient |
| E2E | Full user journeys, multi-turn conversations | httpx, live server |
| Non-functional | Latency, concurrency, CORS, error handling | pytest-timeout |
| Evaluation | Containment rate, tool accuracy, hallucination | AgentEvaluator suite |

All 158+ tests run in offline mock mode with zero external dependencies.

---

## 9. Observability

- **Structured logging:** `structlog` across all modules with consistent key-value pairs
- **Error tracking:** Sentry integration (optional, via `SENTRY_DSN`)
- **Distributed tracing:** OpenTelemetry (optional, via `OTEL_ENDPOINT`)
- **Application metrics:** Prometheus endpoint at `/metrics` exposing request counts, latency, error rates, active sessions, and uptime
- **Health checks:** Deep health endpoint (`/api/v1/observability/health`) and Docker HEALTHCHECK

---

## 10. Performance Characteristics

| Metric | Target | Method |
|---|---|---|
| Response time (chat) | < 1000ms (mock), < 2000ms (LLM) | `pytest-timeout` enforcement |
| Response time (voice) | < 1500ms (STT + LLM + TTS) | End-to-end timing |
| Concurrent sessions | 60+ per instance | Rate-limit at 60 rpm |
| RAG retrieval | < 200ms (semantic), < 50ms (keyword) | ChromaDB + inverted index |
| Test suite | < 90s (158+ tests) | Parallel execution |

---

## 11. Roadmap

| Capability | Status |
|---|---|
| Omnichannel chat + voice + copilot | ✅ Delivered |
| Twilio PSTN integration | ✅ Delivered |
| Amazon Connect adapter | ✅ Delivered |
| RAG with semantic + keyword fallback | ✅ Delivered |
| Multi-tenant auth and isolation | ✅ Delivered |
| Enterprise integrations (HubSpot, Zendesk, Slack, ServiceNow) | ✅ Delivered |
| Automated evaluation and regression testing | ✅ Delivered |
| Feedback loop with auto-adjustment | ✅ Delivered |
| iPaaS webhook support (n8n, Zapier) | ✅ Delivered |
| WebSocket streaming | ✅ Delivered |
| Docker deployment with health checks | ✅ Delivered |
| CI/CD pipeline (lint, test, e2e, docker) | ✅ Delivered |
| Real-time agent monitoring dashboard | 🔄 In Progress |
| Live agent handoff with context passing | 📅 Planned |
| Analytics-driven prompt optimization | 📅 Planned |

---

## 12. Configuration Reference

### 12.1 Core Settings (`.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | No | — | GPT-4o-mini + embeddings |
| `ANTHROPIC_API_KEY` | No | — | Claude models |
| `TWILIO_ACCOUNT_SID` | No | — | PSTN voice calls |
| `TWILIO_AUTH_TOKEN` | No | — | Twilio auth |
| `TWILIO_PHONE_NUMBER` | No | — | Outbound caller ID |
| `HUBSPOT_API_KEY` | No | — | CRM integration |
| `WEBHOOK_SIGNING_SECRET` | No | — | HMAC webhook signing |
| `SETTINGS_ADMIN_TOKEN` | No | — | Admin API protection |
| `SENTRY_DSN` | No | — | Error tracking |
| `OTEL_ENDPOINT` | No | — | OpenTelemetry collector |

### 12.2 Agent Configuration (`config/agents.yaml`)

Defines per-agent LLM provider, model, temperature, max tokens, sampling parameters, tools, and telephony settings (greeting, fallback, silence timeout, transfer number).

---

*Document version 2.0 — For internal and partner use.*  
*Nexus AI Agent Platform — © 2026 Shubham RSY*
