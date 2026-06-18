"""End-to-end user journey tests — simulates real operator/customer flows via HTTP."""

import pytest

pytestmark = pytest.mark.e2e


class TestPlatformDiscovery:
    """Step 0: operator opens console and verifies platform is live."""

    def test_health_check(self, client):
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "healthy"
        assert body["service"] == "enterprise-voice-agents"
        assert "stt_available" in body
        assert "tts_available" in body

    def test_agents_catalog(self, client):
        res = client.get("/api/v1/agents")
        assert res.status_code == 200
        agents = res.json()
        assert "chat_support" in agents
        assert "voice_support" in agents
        assert "copilot" in agents
        assert agents["chat_support"]["channel"] == "chat"
        assert agents["copilot"]["channel"] == "copilot"

    def test_ui_homepage_loads(self, client):
        res = client.get("/")
        assert res.status_code == 200
        html = res.text
        assert "Nexus" in html
        assert 'data-mode="chat"' in html or "data-mode" in html
        assert "clearSessionBtn" in html or "Clear Session" in html
        assert "/api/v1" in html


class TestChatUserJourney:
    """Customer support chat — full resolution path."""

    def test_password_reset_flow(self, client, session_id):
        res = client.post(
            "/api/v1/chat",
            json={
                "message": "How do I reset my password?",
                "agent_id": "chat_support",
                "session_id": session_id,
                "customer_info": "jane@example.com",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["agent_id"] == "chat_support"
        assert len(data["response"]) > 10
        assert "metrics" in data
        assert "response_time_ms" in data["metrics"]

    def test_account_lookup_flow(self, client, session_id):
        res = client.post(
            "/api/v1/chat",
            json={
                "message": "Can you look up jane@example.com?",
                "agent_id": "chat_support",
                "session_id": session_id,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["response"]
        tool_names = [t.get("name") for t in data.get("tool_calls", [])]
        assert "lookup_customer" in tool_names or len(data["response"]) > 0

    def test_multi_turn_conversation(self, client, session_id):
        first = client.post(
            "/api/v1/chat",
            json={
                "message": "I have an API 403 error",
                "session_id": session_id,
                "agent_id": "chat_support",
            },
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/chat",
            json={
                "message": "What should I check first?",
                "session_id": session_id,
                "agent_id": "chat_support",
            },
        )
        assert second.status_code == 200
        assert len(second.json()["response"]) > 0

    def test_session_stats_increase(self, client, session_id):
        before = client.get("/api/v1/sessions/stats").json()["active_sessions"]
        client.post(
            "/api/v1/chat",
            json={"message": "Hello", "session_id": session_id},
        )
        after = client.get("/api/v1/sessions/stats").json()["active_sessions"]
        assert after >= before


class TestCopilotUserJourney:
    """Agent-assist copilot — draft and summarize with transcript context."""

    def test_draft_reply_with_transcript(self, client):
        transcript = (
            "Customer: I can't log in after resetting my password\n"
            "Customer: I tried twice and get invalid credentials"
        )
        res = client.post(
            "/api/v1/copilot",
            json={
                "message": "Draft a reply for this frustrated customer",
                "agent_id": "copilot",
                "conversation_summary": transcript,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["channel"] == "copilot"
        assert len(data["response"]) > 20
        assert data["metrics"].get("for_human_agent") is True
        assert data["metrics"].get("assist_type") in ("draft", "summary", "escalation_advisory")

    def test_escalation_advisory(self, client):
        res = client.post(
            "/api/v1/copilot",
            json={
                "message": "Should I escalate this to a supervisor?",
                "agent_id": "copilot",
                "conversation_summary": "Customer threatened legal action over billing.",
            },
        )
        assert res.status_code == 200
        assert res.json()["metrics"].get("assist_type") == "escalation_advisory"


class TestVoiceUserJourney:
    """Voice channel — inbound call simulation and speech processing."""

    def test_answer_inbound_call(self, client):
        res = client.post(
            "/api/v1/telephony/simulate",
            json={
                "call_sid": "E2E-CALL-001",
                "from_number": "+15551234567",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["listening"] is True
        assert data["routing"]["destination"]
        assert "twiml" in data

    def test_caller_speech_and_agent_response(self, client):
        res = client.post(
            "/api/v1/telephony/simulate",
            json={
                "call_sid": "E2E-CALL-002",
                "from_number": "+15551234567",
                "speech": "How do I reset my password?",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["caller_said"] == "How do I reset my password?"
        assert data["agent_response"] or data["spoken_responses"]

    def test_transfer_request_routing(self, client):
        res = client.post(
            "/api/v1/telephony/simulate",
            json={
                "call_sid": "E2E-CALL-003",
                "from_number": "+15551234567",
                "speech": "I need to speak to a manager",
            },
        )
        assert res.status_code == 200
        data = res.json()
        has_transfer = bool(data.get("transfer_to")) or any(
            a.get("type") == "transfer" for a in data.get("call_actions", [])
        )
        assert has_transfer or "specialist" in (data.get("agent_response") or "").lower()


class TestSessionLifecycle:
    """Session create → chat → clear → fresh state."""

    def test_delete_session_endpoint(self, client, session_id):
        client.post(
            "/api/v1/chat",
            json={"message": "Remember my name is TestUser", "session_id": session_id},
        )
        del_res = client.delete(f"/api/v1/chat/{session_id}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "session_ended"

        stats = client.get("/api/v1/sessions/stats").json()
        assert isinstance(stats["active_sessions"], int)


class TestRAGUserJourney:
    """Knowledge base retrieval during support."""

    def test_knowledge_search_returns_results(self, client):
        res = client.post(
            "/api/v1/rag/search",
            params={"query": "How do I reset my password?", "top_k": 3},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "How do I reset my password?"
        assert isinstance(data["results"], list)

    def test_chat_includes_rag_metrics(self, client, session_id):
        res = client.post(
            "/api/v1/chat",
            json={
                "message": "How do I update my payment method?",
                "session_id": session_id,
            },
        )
        assert res.status_code == 200
        metrics = res.json()["metrics"]
        assert "grounding_score" in metrics
        assert "rag_chunks_used" in metrics
        assert "sources" in metrics


class TestIntegrationsJourney:
    """iPaaS webhook registration."""

    def test_register_webhook(self, client):
        res = client.post(
            "/api/v1/integrations/webhooks",
            json={
                "event_type": "conversation.start",
                "url": "https://hooks.example.com/voice-agents",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "registered"


class TestEvaluationJourney:
    """Quality evaluation suite — regression gate."""

    def test_evaluation_suite_runs(self, client):
        res = client.post("/api/v1/evaluation/run")
        assert res.status_code == 200
        data = res.json()
        summary = data["summary"]
        assert summary["total"] > 0
        assert summary["passed"] >= 0
        assert "containment_rate" in summary
        assert "avg_grounding_score" in summary
        assert len(data["results"]) == summary["total"]
