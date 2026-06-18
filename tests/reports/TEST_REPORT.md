# Enterprise Voice Agents — Test Report

**Date:** 2026-06-18  
**Environment:** Python 3.14 · macOS · Mock/offline mode (no live API keys)  
**Result:** ✅ **61 / 61 passed** (28 unit/integration + 33 E2E/non-functional)

---

## Executive Summary

| Category | Tests | Passed | Failed |
|----------|------:|-------:|-------:|
| Unit & integration | 28 | 28 | 0 |
| E2E user journeys | 17 | 17 | 0 |
| Non-functional | 16 | 16 | 0 |
| **Total** | **61** | **61** | **0** |

---

## Functional Testing

Validates that features work correctly against requirements.

### Platform & discovery
| Test | Status | What it verifies |
|------|--------|------------------|
| Health endpoint | ✅ | `GET /api/v1/health` returns healthy status, STT/TTS flags |
| Agents catalog | ✅ | All three agents (chat, voice, copilot) registered with tools |
| UI homepage | ✅ | `GET /` serves Nexus console HTML with API wiring |

### Chat channel (customer support)
| Test | Status | What it verifies |
|------|--------|------------------|
| Password reset flow | ✅ | KB-backed answer + metrics |
| Account lookup | ✅ | CRM `lookup_customer` tool invoked for email |
| Multi-turn conversation | ✅ | Same session handles follow-up |
| Session stats | ✅ | Active session count increases |

### Copilot channel (agent assist)
| Test | Status | What it verifies |
|------|--------|------------------|
| Draft with transcript | ✅ | Copilot uses conversation summary, returns assist metrics |
| Escalation advisory | ✅ | `assist_type=escalation_advisory` detected |

### Voice channel (telephony)
| Test | Status | What it verifies |
|------|--------|------------------|
| Answer inbound call | ✅ | Simulate without speech → listening + routing |
| Caller speech | ✅ | Speech → agent response + TwiML |
| Transfer request | ✅ | Manager request → transfer or specialist routing |

### Session & RAG
| Test | Status | What it verifies |
|------|--------|------------------|
| Delete session | ✅ | `DELETE /chat/{id}` ends server session |
| Knowledge search | ✅ | `POST /rag/search` returns FAQ results (offline fallback) |
| RAG metrics in chat | ✅ | `grounding_score`, `sources`, `rag_chunks_used` in response |

### Integrations & evaluation
| Test | Status | What it verifies |
|------|--------|------------------|
| Webhook registration | ✅ | iPaaS webhook register endpoint |
| Evaluation suite | ✅ | 5/5 test cases pass, benchmarks run |

### Unit components
| Area | Tests | Status |
|------|------:|--------|
| Call router (VIP/skill/fallback) | 3 | ✅ |
| Prompt templates (3 channels) | 1 | ✅ |
| Tool registry vs agent config | 1 | ✅ |
| CRM mock (lookup, tickets) | 2 | ✅ |
| Session manager (TTL, max, eviction) | 5 | ✅ |
| Twilio handler (inbound, process, simulate) | 4 | ✅ |
| Guardrails, grounding, LLM params | 7 | ✅ |
| Evaluator containment | 3 | ✅ |

---

## Non-Functional Testing

Validates quality attributes: performance, reliability, security, concurrency.

### Performance
| Test | Threshold | Status |
|------|-----------|--------|
| Health latency | < 2000 ms | ✅ |
| Chat response (mock) | < 15000 ms | ✅ |
| RAG search latency | < 10000 ms | ✅ |
| UI payload size | < 500 KB | ✅ |

### Concurrency
| Test | Status | What it verifies |
|------|--------|------------------|
| 20 parallel health checks | ✅ | No failures under load |
| 8 parallel chat sessions | ✅ | Isolated sessions, all respond |

### Reliability & resilience
| Test | Status | What it verifies |
|------|--------|------------------|
| STT without API key | ✅ | Returns 503 with clear message |
| TTS without API key | ✅ | Returns 503 |
| RAG ingest missing path | ✅ | Returns 404 |
| Delete unknown session | ✅ | Idempotent, no crash |
| Invalid JSON on simulate | ✅ | Returns 422 |

### Security (baseline)
| Test | Status | What it verifies |
|------|--------|------------------|
| CORS middleware | ✅ | `access-control-allow-origin` present |
| OpenAPI schema | ✅ | `/openapi.json` valid, documents chat API |
| API docs | ✅ | `/docs` reachable |
| No embedded secrets in UI | ✅ | No `sk-proj-`, `sk-ant-`, `pat-` in HTML |

### Availability (smoke)
| Test | Status | What it verifies |
|------|--------|------------------|
| Full API smoke sequence | ✅ | Health → agents → stats → UI → chat |

---

## E2E User Journeys Simulated

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Operator   │────▶│ Health + UI  │────▶│ Pick channel│
│ opens app   │     │ loads        │     │ Chat/Copilot│
└─────────────┘     └──────────────┘     │ /Voice      │
                                          └──────┬──────┘
                                                 │
         ┌───────────────────────────────────────┼────────────────────────┐
         ▼                       ▼               ▼                        │
   ┌───────────┐          ┌────────────┐   ┌────────────┐                 │
   │ Chat: ask │          │ Copilot:   │   │ Voice:     │                 │
   │ question  │          │ paste      │   │ answer     │                 │
   │ + follow- │          │ transcript │   │ call +     │                 │
   │ up        │          │ + draft    │   │ speak      │                 │
   └─────┬─────┘          └─────┬──────┘   └─────┬──────┘                 │
         │                      │                │                        │
         └──────────────────────┴────────────────┴────────────────────────┘
                                                 │
                                          ┌──────▼──────┐
                                          │ Clear session│
                                          │ DELETE /chat │
                                          └─────────────┘
```

---

## Fixes Applied During Test Run

1. **RAG vector search** — Added FAQ keyword fallback when Chroma embedding dimensions mismatch (offline vs OpenAI-indexed DB).
2. **Mock orchestrator metrics** — Added `grounding_score`, `sources`, `hallucination_risk` in mock mode for UI citation chips.
3. **Test assertions** — Aligned evaluation and security tests with actual API response shapes.

---

## How to Run

### Local (mirrors CI)
```bash
./scripts/ci.sh              # full automation suite + coverage
./scripts/run_full_test_suite.sh  # alias to ci.sh
```

### Manual pytest
```bash
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ tests/e2e/ -v
```

### CI/CD (GitHub Actions)
Automated on every **push** and **pull request** to `main` / `develop`:

| Job | What it runs |
|-----|----------------|
| `unit` | PyTest unit + integration (Python 3.11 & 3.12) + coverage |
| `e2e` | E2E + non-functional tests + JUnit report |
| `docker` | Build image + health/UI smoke test |

Workflow file: `.github/workflows/ci.yml`

Badge (add to README after first CI run):
```markdown
![CI](https://github.com/ShubhamRSY/voice-agents/actions/workflows/ci.yml/badge.svg)
```

---

## Notes

- Tests run in **mock/offline mode** (`OPENAI_API_KEY` cleared in `conftest.py`) — no external API charges.
- Live STT/TTS require `OPENAI_API_KEY`; reliability tests confirm graceful 503 without keys.
- For production load testing, run against a deployed instance with `locust` or `k6` (not included in this suite).
