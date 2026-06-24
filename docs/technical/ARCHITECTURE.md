# Nexus — AI Ops Platform

**Omnichannel AI command centre for customer support.**  
Open source. Chat, copilot, and voice — unified.

---

## What Nexus Does

Nexus replaces three separate tools (live chat, AI copilot, phone system) with one AI-powered console. Agents handle all customer interactions from a single interface, with one AI orchestrator that remembers context across channels.

## Capabilities

| Capability | What It Means |
|---|---|
| **Omnichannel Console** | Chat, copilot (agent-assist), and voice calls in one UI. No tab switching. |
| **Multi-LLM** | Swap between OpenAI, Anthropic Claude, and Google Gemini per conversation. No lock-in. |
| **Live Streaming** | AI responses stream token-by-token via SSE. Operators see answers form in real time. |
| **Voice (PSTN)** | Inbound and outbound calls through Twilio. Live transcription, AI voice responses. |
| **Amazon Connect** | Lambda-style webhook handler for AWS Connect contact flows. |
| **Generic SIP/CCaaS** | Abstract base class to add any SIP or CCaaS provider. |
| **Feedback Engine** | Post-interaction CSAT surveys trigger automatic AI behaviour tuning. No manual tweaking. |
| **RAG** | Retrieval-augmented generation grounded in your knowledge base. Citations on every answer. |
| **Audit Trail** | Every message, tool call, and response logged with timestamps. Compliance-ready. |
| **Encrypted Vault** | API keys stored in AES-256-GCM encrypted database. Never logged or hardcoded. |

## Channels

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   Chat      │   │  Copilot    │   │   Voice     │
│  (Web UI)   │   │  (Web UI)   │   │ (Twilio)    │
├─────────────┤   ├─────────────┤   ├─────────────┤
│ Live chat   │   │ Paste       │   │ Inbound     │
│ with AI     │   │ transcripts │   │ calls       │
│             │   │ Get AI-     │   │ Outbound    │
│             │   │ suggested   │   │ dialler     │
│             │   │ replies     │   │ Live STT    │
│             │   │             │   │ AI TTS      │
└─────────────┘   └─────────────┘   └─────────────┘
```

## Integrations

- **LLMs:** OpenAI GPT-4o, Anthropic Claude 3.5, Google Gemini 2.0
- **Telephony:** Twilio (PSTN + WhatsApp), Amazon Connect, generic SIP/CCaaS
- **CRMs:** Salesforce, Zendesk, ServiceNow
- **Notifications:** Slack
- **iPaaS:** n8n, Zapier — event-driven automation for ticket creation, feedback, escalations

## How It Works

1. A customer messages via chat, calls by phone, or an agent opens Copilot mode.
2. Nexus routes the request to the configured LLM with channel-specific prompts.
3. The AI retrieves relevant knowledge from the vector database (RAG).
4. The response streams back to the operator or is spoken to the caller via TTS.
5. The interaction is logged. If feedback is collected, the engine adjusts behaviour automatically.

## Quick Start

```bash
git clone https://github.com/ShubhamRSY/voice-agents.git
cd voice-agents
pip install -e ".[dev]"
cp .env.example .env    # add your API keys
uvicorn src.main:app --reload --port 8001
```

Open `http://localhost:8001` in a browser.

## Deployment

| Method | Description |
|---|---|
| Docker | `docker compose up` — single-container deployment |
| Bare metal | `uvicorn` behind nginx/Caddy |
| CI/CD | GitHub Actions — lint, unit tests (158+), E2E tests (33) |

## Architecture Overview

```
Web Console  ─┐
Twilio       ─┤
Amazon Conn. ─┤──► FastAPI ──► Agent Orchestrator ──► LLM (OpenAI/Claude/Gemini)
REST API     ─┘                   │
                                  ├──► RAG (vector search + knowledge base)
                                  ├──► Feedback Engine (CSAT auto-adjust)
                                  └──► Integrations (CRM, Slack, iPaaS)
```

All components are part of a single Python application — simple to deploy, simple to operate.

## Project Links

- **Repository:** [github.com/ShubhamRSY/voice-agents](https://github.com/ShubhamRSY/voice-agents)
- **License:** MIT

---

*Nexus AI Ops — one console for every conversation.*
