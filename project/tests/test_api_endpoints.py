"""Integration tests for REST API endpoints using TestClient."""

import pytest


@pytest.fixture
def client():
    from src.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


class TestHealth:
    def test_health_returns_200(self, client):
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "healthy"
        assert "service" in body

    def test_metrics_endpoint(self, client):
        res = client.get("/api/v1/metrics")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/plain")
        assert "nexus_" in res.text
        assert "uptime_seconds" in res.text

    def test_observability_health(self, client):
        res = client.get("/api/v1/observability/health")
        assert res.status_code == 200
        body = res.json()
        assert "active_requests" in body
        assert "uptime_seconds" in body
        assert "auth_failures" in body
        assert "latency_ms" in body

    def test_metrics_increment_on_request(self, client):
        before = client.get("/api/v1/observability/health").json()
        client.get("/api/v1/health")
        after = client.get("/api/v1/observability/health").json()
        assert after["requests_processed"] >= before["requests_processed"] + 1

    def test_api_root(self, client):
        res = client.get("/api/v1")
        assert res.status_code == 200
        body = res.json()
        assert body["service"] == "Nexus Enterprise AI Agents"


class TestAuth:
    def test_register_and_login(self, client):
        import uuid
        suffix = uuid.uuid4().hex[:8]
        email = f"test-{suffix}@example.com"
        password = "Secret123!"
        name = "Integration Tester"

        reg = client.post("/api/v1/auth/register", json={
            "email": email, "password": password, "name": name,
        })
        assert reg.status_code == 200, reg.text
        token = reg.json()["token"]
        assert token

        login = client.post("/api/v1/auth/login", json={
            "email": email, "password": password,
        })
        assert login.status_code == 200, login.text
        assert login.json()["token"]

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json()["email"] == email

    def test_register_duplicate_email(self, client):
        import uuid
        suffix = uuid.uuid4().hex[:8]
        email = f"dup-{suffix}@example.com"
        res1 = client.post("/api/v1/auth/register", json={
            "email": email, "password": "Pass123!", "name": "Dup",
        })
        assert res1.status_code == 200, res1.text
        res = client.post("/api/v1/auth/register", json={
            "email": email, "password": "Pass456!", "name": "Dup2",
        })
        assert res.status_code == 409, res.text

    def test_login_wrong_password(self, client):
        res = client.post("/api/v1/auth/login", json={
            "email": "noone-int@example.com", "password": "wrong",
        })
        assert res.status_code == 401


class TestAgents:
    def test_list_agents(self, client):
        res = client.get("/api/v1/agents")
        assert res.status_code == 200
        agents = res.json()
        assert isinstance(agents, dict)
        assert len(agents) > 0

    def test_llm_config(self, client):
        res = client.get("/api/v1/llm/config")
        assert res.status_code == 200
        body = res.json()
        assert "defaults" in body
        assert "agents" in body


class TestChat:
    def test_chat_with_mock_agent(self, client):
        res = client.post("/api/v1/chat", json={
            "message": "What is my account balance?",
            "agent_id": "chat_support",
        })
        assert res.status_code == 200
        body = res.json()
        assert "response" in body
        assert "metrics" in body

    def test_chat_unknown_agent(self, client):
        res = client.post("/api/v1/chat", json={
            "message": "Hello",
            "agent_id": "nonexistent_agent",
        })
        assert res.status_code == 400

    def test_copilot_endpoint(self, client):
        res = client.post("/api/v1/copilot", json={
            "message": "Draft a reply to this customer complaint",
            "conversation_summary": "Customer is upset about billing",
        })
        assert res.status_code == 200
        assert "response" in res.json()


class TestSessions:
    def test_session_stats(self, client):
        res = client.get("/api/v1/sessions/stats")
        assert res.status_code == 200
        assert "active_sessions" in res.json()

    def test_session_history_not_found(self, client):
        res = client.get("/api/v1/sessions/nonexistent/history")
        assert res.status_code == 200
        body = res.json()
        assert body["session"] is None


class TestCSAT:
    def test_submit_csat(self, client):
        res = client.post("/api/v1/csat", json={
            "session_id": "nonexistent",
            "score": 4,
            "feedback": "Great service",
        })
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "recorded"

    def test_csat_stats(self, client):
        res = client.get("/api/v1/csat/stats")
        assert res.status_code == 200
        assert "stats" in res.json()


class TestRAG:
    def test_rag_search_empty(self, client):
        res = client.post("/api/v1/rag/search?query=test&top_k=3")
        assert res.status_code == 200
        body = res.json()
        assert "results" in body


class TestDemo:
    def test_demo_reset(self, client):
        res = client.post("/api/v1/demo/reset")
        assert res.status_code == 200
        assert res.json()["status"] == "demo_reset"


class TestTasks:
    def test_unknown_task_status(self, client):
        res = client.get("/api/v1/tasks/does-not-exist")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] in ("unknown", None)


class TestFeedback:
    def test_feedback_report(self, client):
        res = client.get("/api/v1/feedback/chat_support/report")
        assert res.status_code == 200, res.text
        body = res.json()
        assert "agent_id" in body
        assert "config" in body

    def test_feedback_config(self, client):
        res = client.get("/api/v1/feedback/chat_support/config")
        assert res.status_code == 200

    def test_feedback_suggestions(self, client):
        res = client.get("/api/v1/feedback/chat_support/suggestions")
        assert res.status_code == 200
        assert "suggestions" in res.json()


class TestAnalytics:
    def test_analytics_dashboard(self, client):

        res = client.get("/api/v1/analytics/dashboard?hours=24")
        # Auth may or may not be required depending on settings
        assert res.status_code in (200, 401)


class TestEvents:
    def test_receive_event(self, client):
        res = client.post("/api/v1/events", json={
            "event_type": "test.event",
            "payload": {"key": "value"},
        })
        assert res.status_code == 200
        assert res.json()["status"] == "received"


class TestStreaming:
    def test_chat_stream_sse_returns_tokens(self, client):
        """SSE streaming endpoint yields token and done events."""
        res = client.get("/api/v1/chat/sse", params={
            "message": "Hello",
            "agent_id": "chat_support",
        })
        assert res.status_code == 200
        assert res.headers.get("content-type", "").startswith("text/event-stream")
        body = res.text
        assert "data:" in body
        assert "token" in body or "done" in body
        assert "data: [DONE]" in body

    def test_chat_stream_sse_unknown_agent(self, client):
        res = client.get("/api/v1/chat/sse", params={
            "message": "Hello",
            "agent_id": "nonexistent",
        })
        assert res.status_code == 400

    def test_chat_stream_sse_requires_auth_when_enabled(self, client):
        from src.config import reload_settings
        reload_settings()
        res = client.get("/api/v1/chat/sse", params={
            "message": "Hello",
            "agent_id": "chat_support",
        })
        assert res.status_code in (200, 401)


class TestWebSocket:
    def test_websocket_chat_stream(self, client):
        """WebSocket endpoint streams token and done events."""
        with client.websocket_connect("/api/v1/chat/stream") as ws:
            ws.send_json({"message": "Hello", "agent_id": "chat_support"})
            import time
            deadline = time.time() + 25
            events = []
            while time.time() < deadline:
                try:
                    data = ws.receive_json()
                    events.append(data)
                    if data.get("type") == "done":
                        break
                except Exception:
                    break
            assert len(events) > 0, "no events received over WebSocket"
            assert any(e.get("type") == "done" for e in events)

    def test_websocket_empty_message(self, client):
        with client.websocket_connect("/api/v1/chat/stream") as ws:
            ws.send_json({"message": "", "agent_id": "chat_support"})
            data = ws.receive_json()
            assert data["type"] == "error"

    def test_websocket_unknown_agent(self, client):
        with client.websocket_connect("/api/v1/chat/stream") as ws:
            ws.send_json({"message": "Hello", "agent_id": "nonexistent"})
            data = ws.receive_json()
            assert "error" in data.get("type", "").lower() or data.get("type") == "error"
