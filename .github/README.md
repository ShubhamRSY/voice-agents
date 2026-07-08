<div align="center">

# Nexus

**Purpose-built AI agents. One CX platform. (Open-source)**  
Nexus is an omnichannel AI agent platform for customer experience teams — one orchestrator for **Chat**, **Copilot**, and **Voice**, grounded with **RAG**, protected by **JWT auth + guardrails**, and built for **operations** (streaming, rate limits, logs, backups).

[![CI](https://github.com/ShubhamRSY/voice-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/ShubhamRSY/voice-agents/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](project/LICENSE)
[![Tests](https://img.shields.io/badge/tests-109%20unit%20passing-brightgreen.svg)](project/tests/)

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

See `project/README.md` for the full changelog and deployment details.

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

Open `http://127.0.0.1:8001`.

Production console (example): `https://yournexus.duckdns.org/`

---

## Production Deployment

See `project/docs/deploy-oracle-duckdns.md`.

---

## Architecture

See `project/docs/overview.md`.

---

## Features / API / Testing / Contributing / License

See the full documentation in `project/README.md`.

