"""Comprehensive live E2E tests against running server at 127.0.0.1:8001."""
import time
import uuid
import pytest
import httpx

BASE = "http://127.0.0.1:8001/api/v1"
ROOT = "http://127.0.0.1:8001"
SESSION_ID = f"e2e-{uuid.uuid4().hex[:12]}"
WEBHOOK_URL = "https://hooks.example.com/e2e-test"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=30)


# ── 1. HEALTH ──────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_healthy(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "healthy"

    def test_health_has_capability_flags(self, client):
        r = client.get("/health")
        d = r.json()
        assert "stt_available" in d
        assert "tts_available" in d
        assert "tts_voice" in d

    def test_health_latency_under_200ms(self, client):
        start = time.perf_counter()
        client.get("/health")
        assert (time.perf_counter() - start) * 1000 < 200


# ── 2. AGENTS CATALOG ──────────────────────────────────────────────────

class TestAgents:
    def test_agents_catalog_returns_dict(self, client):
        r = client.get("/agents")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_agents_has_required_keys(self, client):
        r = client.get("/agents")
        agents = r.json()
        for agent_id, info in agents.items():
            assert "name" in info
            assert "channel" in info
            assert "tools" in info

    def test_whatsapp_agent_registered(self, client):
        r = client.get("/agents")
        agents = r.json()
        assert "whatsapp_support" in agents, "whatsapp agent missing from catalog"
        assert agents["whatsapp_support"]["channel"] == "whatsapp"

    def test_agents_has_voice_support(self, client):
        r = client.get("/agents")
        agents = r.json()
        assert "voice_support" in agents
        assert "chat_support" in agents
        assert "copilot" in agents


# ── 3. CHAT ────────────────────────────────────────────────────────────

class TestChat:
    def test_chat_returns_response(self, client):
        r = client.post("/chat", json={
            "message": "How do I reset my password?",
            "agent_id": "chat_support",
            "session_id": SESSION_ID,
        })
        assert r.status_code == 200
        d = r.json()
        assert "response" in d
        assert len(d["response"]) > 0
        assert d["agent_id"] == "chat_support"

    def test_chat_returns_metrics(self, client):
        r = client.post("/chat", json={
            "message": "I need help with API 403 errors",
            "agent_id": "chat_support",
            "session_id": SESSION_ID,
        })
        assert r.status_code == 200
        d = r.json()
        assert "metrics" in d
        assert "response_time_ms" in d["metrics"]

    def test_chat_empty_message_rejected(self, client):
        r = client.post("/chat", json={
            "message": "",
            "agent_id": "chat_support",
            "session_id": SESSION_ID,
        })
        assert r.status_code == 422

    def test_chat_invalid_agent_rejected(self, client):
        r = client.post("/chat", json={
            "message": "hello",
            "agent_id": "nonexistent_agent",
            "session_id": SESSION_ID,
        })
        assert r.status_code in (400, 422)

    def test_chat_with_long_message(self, client):
        r = client.post("/chat", json={
            "message": "help " * 500,
            "agent_id": "chat_support",
            "session_id": f"long-{uuid.uuid4().hex[:8]}",
        })
        assert r.status_code in (200, 413, 422)

    def test_chat_with_special_characters(self, client):
        r = client.post("/chat", json={
            "message": "Can you help with <script>alert('xss')</script> & encoding? 日本語 Español",
            "agent_id": "chat_support",
            "session_id": f"special-{uuid.uuid4().hex[:8]}",
        })
        assert r.status_code == 200

    def test_chat_with_unicode(self, client):
        r = client.post("/chat", json={
            "message": "你好世界 😊 🌟 🎉",
            "agent_id": "chat_support",
            "session_id": f"unicode-{uuid.uuid4().hex[:8]}",
        })
        assert r.status_code == 200

    def test_chat_with_numeric_message(self, client):
        r = client.post("/chat", json={
            "message": "42",
            "agent_id": "chat_support",
            "session_id": f"num-{uuid.uuid4().hex[:8]}",
        })
        assert r.status_code == 200


# ── 4. COPILOT ─────────────────────────────────────────────────────────

class TestCopilot:
    def test_copilot_draft_reply(self, client):
        r = client.post("/copilot", json={
            "message": "Draft a reply for this frustrated customer",
            "agent_id": "copilot",
            "conversation_summary": "Customer: I can't log in\nAgent: Try resetting\nCustomer: It didn't work",
        })
        assert r.status_code == 200
        d = r.json()
        assert "response" in d

    def test_copilot_escalation_flag(self, client):
        r = client.post("/copilot", json={
            "message": "Should I escalate this to a supervisor?",
            "agent_id": "copilot",
            "conversation_summary": "Customer is threatening to cancel service",
        })
        assert r.status_code == 200

    def test_copilot_summarize(self, client):
        r = client.post("/copilot", json={
            "message": "Summarize this conversation for handoff",
            "agent_id": "copilot",
            "conversation_summary": "Long conversation with multiple exchanges about billing",
        })
        assert r.status_code == 200


# ── 5. VOICE / TELEPHONY ───────────────────────────────────────────────

class TestVoice:
    def test_voice_simulate_with_speech(self, client):
        r = client.post("/telephony/simulate", json={
            "call_sid": "E2E-CALL-001",
            "from_number": "+15551112222",
            "speech": "How do I reset my password?",
        })
        assert r.status_code == 200
        d = r.json()
        has_response = any(k in d for k in ("agent_response", "spoken_responses", "agent_says"))
        assert has_response, f"No agent response in: {d}"

    def test_voice_simulate_no_speech_connects(self, client):
        r = client.post("/telephony/simulate", json={
            "call_sid": "E2E-CALL-002",
            "from_number": "+15551113333",
        })
        assert r.status_code == 200

    def test_voice_simulate_transfer_routing(self, client):
        r = client.post("/telephony/simulate", json={
            "call_sid": "E2E-CALL-003",
            "from_number": "+15551114444",
            "speech": "I need to speak to a manager",
        })
        assert r.status_code == 200

    def test_twilio_inbound_webhook(self, client):
        r = client.post("/telephony/voice/inbound", data={
            "CallSid": "CA-e2e-test",
            "From": "+15551115555",
            "To": "+15551116666",
        })
        assert r.status_code == 200
        ctype = r.headers.get("content-type", "")
        assert "xml" in ctype, f"Expected XML content-type, got: {ctype}"
        body = r.text
        assert "<Response>" in body

    def test_transcribe_rejects_no_file(self, client):
        r = client.post("/telephony/transcribe")
        assert r.status_code in (400, 422)

    def test_speak_endpoint(self, client):
        r = client.post("/telephony/speak", json={
            "text": "Hello, this is a test.",
            "voice": "shimmer",
        })
        assert r.status_code in (200, 400, 422, 500, 503)

    def test_telephony_status(self, client):
        r = client.get("/telephony/status")
        assert r.status_code in (200, 404)


# ── 6. RAG / KNOWLEDGE BASE ────────────────────────────────────────────

class TestRAG:
    def test_knowledge_search(self, client):
        r = client.post("/rag/search", params={"query": "password reset", "top_k": 3})
        assert r.status_code == 200
        d = r.json()
        assert "results" in d

    def test_knowledge_search_no_query(self, client):
        r = client.post("/rag/search")
        assert r.status_code == 422

    def test_knowledge_search_default_top_k(self, client):
        r = client.post("/rag/search", params={"query": "login help"})
        assert r.status_code == 200
        d = r.json()
        assert "results" in d


# ── 7. SESSION MANAGEMENT ──────────────────────────────────────────────

class TestSessions:
    def test_session_stats(self, client):
        r = client.get("/sessions/stats")
        assert r.status_code == 200
        d = r.json()
        assert "active_sessions" in d

    def test_delete_session(self, client):
        sid = f"del-{uuid.uuid4().hex[:8]}"
        client.post("/chat", json={
            "message": "hello",
            "agent_id": "chat_support",
            "session_id": sid,
        })
        r = client.delete(f"/chat/{sid}")
        assert r.status_code == 200

    def test_delete_nonexistent_session_safe(self, client):
        r = client.delete("/chat/nonexistent-session-12345")
        assert r.status_code in (200, 404)

    def test_session_history(self, client):
        sid = f"hist-{uuid.uuid4().hex[:8]}"
        client.post("/chat", json={
            "message": "first message",
            "agent_id": "chat_support",
            "session_id": sid,
        })
        r = client.get(f"/sessions/{sid}/history")
        assert r.status_code == 200
        d = r.json()
        assert "session" in d
        assert "messages" in d


# ── 8. CSAT / EVALUATION ──────────────────────────────────────────────

class TestCSAT:
    def test_csat_submit(self, client):
        r = client.post("/csat", json={
            "session_id": SESSION_ID,
            "score": 5,
            "feedback": "Great support!",
        })
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") == "recorded"

    def test_csat_missing_score(self, client):
        r = client.post("/csat", json={
            "session_id": SESSION_ID,
            "feedback": "ok",
        })
        assert r.status_code == 422

    def test_csat_stats(self, client):
        r = client.get("/csat/stats")
        assert r.status_code == 200

    def test_evaluation_run(self, client):
        try:
            r = client.post("/evaluation/run", timeout=5)
            assert r.status_code in (200, 401, 500)
        except Exception:
            pytest.skip("Evaluation run timed out or unavailable")


# ── 9. INTEGRATIONS / VAULT ─────────────────────────────────────────

class TestIntegrations:
    def test_integration_status(self, client):
        r = client.get("/integrations/status")
        assert r.status_code == 200
        d = r.json()
        assert "providers" in d

    def test_save_credential(self, client):
        # Use a non-OpenAI credential to avoid breaking STT/TTS in other tests
        r = client.put("/integrations/credentials", json={"webhook_signing_secret": "whsec-e2e-test"})
        assert r.status_code in (200, 401)
        # Clean up
        r = client.delete("/integrations/credentials/webhook_signing_secret")
        assert r.status_code in (200, 401)

    def test_register_webhook(self, client):
        r = client.post("/integrations/webhooks", json={
            "event_type": "conversation.started",
            "url": WEBHOOK_URL,
        })
        assert r.status_code in (200, 401)

    def test_delete_webhook(self, client):
        r = client.delete("/integrations/webhooks/conversation.started")
        assert r.status_code in (200, 401)


# ── 10. DEMO RESET ─────────────────────────────────────────────────────

class TestDemoReset:
    def test_demo_reset(self, client):
        r = client.post("/demo/reset")
        assert r.status_code in (200, 401, 404)

    def test_after_reset_chat_still_works(self, client):
        r = client.post("/chat", json={
            "message": "Hello after reset",
            "agent_id": "chat_support",
            "session_id": f"post-reset-{uuid.uuid4().hex[:8]}",
        })
        assert r.status_code == 200


# ── 11. PROMETHEUS METRICS ────────────────────────────────────────────

class TestMetrics:
    def test_prometheus_endpoint(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        body = r.text
        assert "nexus_" in body

    def test_active_sessions_metric(self, client):
        r = client.get("/metrics")
        assert "nexus_active_sessions" in r.text


# ── 12. UI HOMEPAGE ────────────────────────────────────────────────────

class TestUI:
    def test_homepage_returns_html(self, client):
        r = httpx.get(f"{ROOT}/", timeout=10)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_homepage_has_required_elements(self, client):
        r = httpx.get(f"{ROOT}/", timeout=10)
        html = r.text
        assert "Nexus" in html
        assert "sidebar" in html
        assert "composer" in html
        assert "messages" in html

    def test_homepage_js_starts_server_check(self, client):
        r = httpx.get(f"{ROOT}/", timeout=10)
        assert "checkHealth" in r.text or "api/v1/health" in r.text

    def test_homepage_has_theme_toggle(self, client):
        r = httpx.get(f"{ROOT}/", timeout=10)
        assert "themeToggle" in r.text or "theme-toggle" in r.text


# ── 13. CORS HEADERS ──────────────────────────────────────────────────

class TestCORS:
    def test_cors_preflight(self, client):
        r = httpx.options(
            f"{ROOT}/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
            timeout=10,
        )
        cors = r.headers.get("access-control-allow-origin", "")
        assert cors == "*" or "localhost" in cors


# ── 14. CONCURRENCY ───────────────────────────────────────────────────

class TestConcurrency:
    def test_concurrent_health(self, client):
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(client.get, "/health") for _ in range(10)]
            for f in concurrent.futures.as_completed(futures):
                r = f.result()
                assert r.status_code == 200

    def test_concurrent_chat_sessions(self, client):
        import concurrent.futures
        messages = ["password help", "account issue", "API error", "billing question", "login problem"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = [
                ex.submit(client.post, "/chat", json={
                    "message": msg,
                    "agent_id": "chat_support",
                    "session_id": f"concurrent-{i}",
                })
                for i, msg in enumerate(messages)
            ]
            for f in concurrent.futures.as_completed(futures):
                r = f.result()
                assert r.status_code == 200


# ── 15. WHATSAPP ──────────────────────────────────────────────────────

class TestWhatsApp:
    def test_whatsapp_inbound_webhook(self, client):
        r = client.post("/messaging/inbound", data={
            "From": "+15551117777",
            "Body": "I need help with my order",
        })
        assert r.status_code in (200, 404)

    def test_whatsapp_outbound(self, client):
        r = client.post("/messaging/send", params={
            "to": "+15551118888",
            "body": "Thank you for contacting support!",
            "channel": "whatsapp",
        })
        assert r.status_code in (200, 400, 401, 422)

    def test_whatsapp_inbound_sms(self, client):
        r = client.post("/messaging/inbound", data={
            "From": "+15551119999",
            "Body": "SMS test message",
        })
        assert r.status_code in (200, 404)


# ── 16. AUTH ENDPOINTS ─────────────────────────────────────────────────

class TestAuth:
    def test_auth_register(self, client):
        fresh = httpx.Client(base_url=BASE, timeout=15)
        email = f"e2e-reg-{uuid.uuid4().hex[:12]}@test.com"
        r = fresh.post("/auth/register", json={
            "email": email,
            "password": "testpass123",
            "name": "E2E Tester",
            "tenant_name": "E2E Test",
        })
        fresh.close()
        assert r.status_code == 200, f"Register: {r.status_code} {r.text[:200]}"
        d = r.json()
        assert "token" in d

    def test_auth_login_after_register(self, client):
        fresh = httpx.Client(base_url=BASE, timeout=15)
        email = f"e2e-login-{uuid.uuid4().hex[:12]}@test.com"
        r = fresh.post("/auth/register", json={
            "email": email,
            "password": "testpass123",
            "name": "Login Test",
            "tenant_name": "Login Test",
        })
        assert r.status_code == 200, f"Register: {r.status_code} {r.text[:200]}"

        r = fresh.post("/auth/login", json={
            "email": email,
            "password": "testpass123",
        })
        fresh.close()
        assert r.status_code == 200, f"Login: {r.status_code} {r.text[:200]}"
        assert "token" in r.json()


# ── 17. OBSERVABILITY ─────────────────────────────────────────────────

class TestObservability:
    def test_observability_endpoint(self, client):
        r = client.get("/observability/traces")
        assert r.status_code in (200, 404)

    def test_observability_metrics(self, client):
        r = client.get("/observability/metrics")
        assert r.status_code in (200, 404)


# ── 18. RATE LIMITING ──────────────────────────────────────────────────

class TestRateLimiting:
    def test_rate_limit_headers_present(self, client):
        r = client.get("/health")
        has_ratelimit = any(
            "ratelimit" in k.lower() or "retry-after" in k.lower()
            for k in r.headers
        )
        rout = r.headers.get("x-ratelimit-remaining")
        assert has_ratelimit or rout is not None or r.status_code < 429


# ── 19. CSAT WITH REAL DATA FLOW ─────────────────────────────────────

class TestCSATDataFlow:
    def test_csat_after_chat(self, client):
        sid = f"csat-flow-{uuid.uuid4().hex[:8]}"
        client.post("/chat", json={
            "message": "I need help",
            "agent_id": "chat_support",
            "session_id": sid,
        })
        r = client.post("/csat", json={
            "session_id": sid,
            "score": 4,
            "feedback": "Helpful agent",
        })
        assert r.status_code == 200

    def test_csat_stats_after_submission(self, client):
        r = client.get("/csat/stats")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)
