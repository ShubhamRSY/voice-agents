# Enterprise Voice & Chat AI Agent Platform

A production-ready platform demonstrating the full stack of an **AI Agent Engineer** role: voice agents, chat agents, AI copilots, RAG, telephony, CRM integrations, evaluation frameworks, and workflow orchestration.

Built to showcase hands-on skills in prompt design, API integration, telephony (Twilio/SIP/PSTN), LLM orchestration (LangChain/LangGraph), and enterprise deployment patterns.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Gateway                          │
│  /chat  /copilot  /telephony  /rag  /evaluation  /agents    │
└──────────┬──────────┬──────────┬──────────┬──────────────────┘
           │          │          │          │
    ┌──────▼──┐ ┌─────▼────┐ ┌──▼───┐ ┌───▼────────┐
    │  Chat   │ │  Voice   │ │ Copilot│ │ Evaluation│
    │  Agent  │ │  Agent   │ │ Agent  │ │ Framework │
    └──────┬──┘ └─────┬────┘ └───┬───┘ └───────────┘
           │          │          │
    ┌──────▼──────────▼──────────▼──────────────────┐
    │           LangGraph Orchestrator               │
    │    (Prompt Templates + Tool Calling + RAG)     │
    └──────┬──────────┬──────────┬──────────────────┘
           │          │          │
    ┌──────▼──┐ ┌─────▼────┐ ┌──▼────────┐
    │ ChromaDB│ │ HubSpot  │ │  Twilio   │
    │  (RAG)  │ │  (CRM)   │ │ (Voice)   │
    └─────────┘ └──────────┘ └───────────┘
```

## What's Included

| Capability | Implementation |
|---|---|
| **Voice Agents** | Twilio webhook handlers, speech-to-text, TTS responses, human transfer |
| **Chat Agents** | REST API with session management, tool calling |
| **AI Copilot** | Agent-assist with draft responses and conversation summaries |
| **Prompt Design** | Channel-specific templates (voice/chat/copilot) with YAML config |
| **RAG Pipeline** | Document ingestion, chunking, ChromaDB vector store, retrieval |
| **LLM Support** | OpenAI, Anthropic, Gemini via unified factory |
| **Orchestration** | LangGraph ReAct agents with tool routing |
| **CRM Integration** | HubSpot API adapter with mock fallback |
| **Webhooks / iPaaS** | n8n/Zapier-compatible event dispatch |
| **Telephony** | SIP header extraction, call routing, fallback config |
| **Evaluation** | Test suites measuring containment, tool accuracy, latency |

## Quick Start

### 1. Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Optional: add your OPENAI_API_KEY (and optionally ANTHROPIC_API_KEY, Twilio creds)
```

### Credential-free demo mode (recommended to start)

This repo supports a **no-keys-required** demo mode:

- Agents run in `mock` mode (rule-based tool selection)
- RAG uses local deterministic embeddings (no OpenAI embeddings required)
- CRM uses a mock fallback unless you add HubSpot creds

You can run everything (API, tests, demo scripts) without any external accounts.

### 2. Ingest Knowledge Base

```bash
python scripts/ingest_kb.py data/knowledge_base/
```

### 3. Start the Server

```bash
python -m src.main
# API docs at http://localhost:8000/docs
```

### 4. Try It

```bash
# Chat with the agent
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I reset my password?", "session_id": "demo-1"}'

# Search knowledge base
curl -X POST "http://localhost:8000/api/v1/rag/search?query=API+rate+limits&top_k=3"

# List configured agents
curl http://localhost:8000/api/v1/agents

# Run evaluation suite (requires API key)
python scripts/run_evaluation.py
```

## Telephony Setup (Twilio)

1. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER` in `.env`
2. Expose your local server with ngrok: `ngrok http 8000`
3. Set `TWILIO_WEBHOOK_BASE_URL` to your ngrok URL
4. Configure your Twilio phone number voice webhook to:
   - **Inbound**: `POST {WEBHOOK_BASE_URL}/api/v1/telephony/voice/inbound`
   - **Status callback**: `POST {WEBHOOK_BASE_URL}/api/v1/telephony/voice/status`

## iPaaS (n8n / Zapier) Integrations

This platform emits lifecycle events (conversation started/ended, ticket created, escalations) to external systems via webhooks, which can be wired into iPaaS tools like **n8n** or **Zapier**.

### Event schema

Every outbound webhook payload is:

```json
{ "event": "conversation.started", "data": { "...": "..." } }
```

If you configure a shared secret (see below), the request includes an HMAC signature header:

- `X-Webhook-Signature`: hex sha256 of the raw request body

### Register a webhook URL

```bash
curl -X POST http://localhost:8000/api/v1/integrations/webhooks \
  -H "Content-Type: application/json" \
  -d '{"event_type":"conversation.started","url":"https://hooks.zapier.com/hooks/catch/XXXX/YYYY"}'
```

### Templates

- `integrations/templates/n8n-workflow.json` — import into n8n
- `integrations/templates/zapier-setup.md` — Zapier “Catch Hook” setup + mapping notes

## Agent Configuration

Agents are defined in `config/agents.yaml`. Each agent specifies:

- LLM provider and model
- Channel (voice / chat / copilot)
- Available tools
- Temperature and token limits
- Containment targets
- Telephony settings (for voice agents)

## Project Structure

```
├── config/agents.yaml          # Agent definitions and RAG settings
├── data/knowledge_base/        # Sample KB documents
├── scripts/
│   ├── demo_chat.py            # Interactive chat demo
│   ├── ingest_kb.py            # KB ingestion CLI
│   └── run_evaluation.py       # Evaluation runner
├── src/
│   ├── agents/tools.py         # LangChain tool definitions
│   ├── api/routes.py           # REST API endpoints
│   ├── evaluation/evaluator.py # Containment & quality testing
│   ├── integrations/
│   │   ├── crm.py              # HubSpot CRM adapter
│   │   └── webhooks.py         # iPaaS webhook dispatcher
│   ├── llm/factory.py          # Multi-provider LLM factory
│   ├── prompts/templates.py    # Channel-specific prompts
│   ├── rag/                    # Ingestion, vector store, retriever
│   ├── telephony/              # Twilio handler, call router
│   └── workflows/orchestrator.py # LangGraph agent orchestration
└── tests/
    ├── evaluation/test_cases.json
    └── test_platform.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/chat` | Chat with an agent |
| POST | `/api/v1/copilot` | Agent-assist copilot |
| DELETE | `/api/v1/chat/{session_id}` | End a chat session |
| POST | `/api/v1/rag/ingest` | Ingest documents |
| POST | `/api/v1/rag/search` | Search knowledge base |
| POST | `/api/v1/telephony/voice/inbound` | Twilio inbound webhook |
| POST | `/api/v1/telephony/voice/process` | Twilio speech processing |
| POST | `/api/v1/integrations/webhooks` | Register webhook URLs |
| POST | `/api/v1/evaluation/run` | Run evaluation suite |
| GET | `/api/v1/agents` | List configured agents |

## Running Tests

```bash
pytest tests/ -v
```

## Environment Variables

See `.env.example` for all configuration options. At minimum you need:

- `OPENAI_API_KEY` — for LLM and embeddings
- Optionally `ANTHROPIC_API_KEY` — for copilot agent
- Optionally Twilio credentials — for voice telephony
