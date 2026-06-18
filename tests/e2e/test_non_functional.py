"""Non-functional tests — performance, reliability, concurrency, and resilience."""

import concurrent.futures
import time

import pytest

pytestmark = pytest.mark.nfr


class TestPerformance:
    """Response time and throughput expectations."""

    def test_health_latency(self, client):
        start = time.perf_counter()
        res = client.get("/api/v1/health")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert res.status_code == 200
        assert elapsed_ms < 2000, f"Health took {elapsed_ms:.0f}ms (limit 2000ms)"

    def test_chat_mock_latency(self, client, session_id):
        start = time.perf_counter()
        res = client.post(
            "/api/v1/chat",
            json={"message": "Hello", "session_id": session_id},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert res.status_code == 200
        assert elapsed_ms < 15000, f"Chat took {elapsed_ms:.0f}ms (limit 15000ms)"

    def test_ui_payload_size_reasonable(self, client):
        res = client.get("/")
        assert res.status_code == 200
        size_kb = len(res.content) / 1024
        assert size_kb < 500, f"UI is {size_kb:.0f}KB — investigate bloat"

    def test_rag_search_latency(self, client):
        start = time.perf_counter()
        res = client.post(
            "/api/v1/rag/search",
            params={"query": "billing", "top_k": 2},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert res.status_code == 200
        assert elapsed_ms < 10000, f"RAG search took {elapsed_ms:.0f}ms"


class TestConcurrency:
    """Parallel request handling."""

    def test_concurrent_health_checks(self, client):
        def hit_health():
            r = client.get("/api/v1/health")
            return r.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            codes = list(pool.map(lambda _: hit_health(), range(20)))
        assert all(c == 200 for c in codes)

    def test_concurrent_chat_sessions(self, client):
        def chat_once(i: int):
            sid = f"concurrent-{i}"
            r = client.post(
                "/api/v1/chat",
                json={"message": f"Test message {i}", "session_id": sid},
            )
            return r.status_code, len(r.json().get("response", ""))

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(chat_once, range(8)))
        assert all(code == 200 for code, _ in results)
        assert all(length > 0 for _, length in results)


class TestReliability:
    """Graceful degradation and error handling."""

    def test_stt_requires_api_key(self, client):
        res = client.post(
            "/api/v1/telephony/transcribe",
            files={"audio": ("test.webm", b"fake-audio-bytes", "audio/webm")},
        )
        assert res.status_code == 503
        assert "OPENAI_API_KEY" in res.json()["detail"]

    def test_tts_requires_api_key(self, client):
        res = client.post(
            "/api/v1/telephony/speak",
            json={"text": "Hello from the voice agent"},
        )
        assert res.status_code == 503

    def test_rag_ingest_missing_path(self, client):
        res = client.post(
            "/api/v1/rag/ingest",
            json={"source_path": "/nonexistent/path/docs.md"},
        )
        assert res.status_code == 404

    def test_delete_unknown_session_is_safe(self, client):
        res = client.delete("/api/v1/chat/never-created-session-xyz")
        assert res.status_code == 200
        assert res.json()["status"] == "session_ended"

    def test_voice_simulate_invalid_json_rejected(self, client):
        res = client.post(
            "/api/v1/telephony/simulate",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 422


class TestSecurityBasics:
    """Baseline security checks (non-exhaustive)."""

    def test_cors_middleware_active(self, client):
        res = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        assert "access-control-allow-origin" in res.headers

    def test_api_docs_available(self, client):
        res = client.get("/docs")
        assert res.status_code == 200

    def test_openapi_schema_valid(self, client):
        res = client.get("/openapi.json")
        assert res.status_code == 200
        schema = res.json()
        assert schema["info"]["title"]
        assert "/api/v1/chat" in schema["paths"]

    def test_ui_does_not_embed_api_keys(self, client):
        html = client.get("/").text
        assert "sk-proj-" not in html
        assert "sk-ant-" not in html
        assert "pat-" not in html


class TestAvailability:
    """Core endpoints remain reachable in sequence (smoke)."""

    def test_full_api_smoke_sequence(self, client, session_id):
        endpoints = [
            ("GET", "/api/v1/health"),
            ("GET", "/api/v1/agents"),
            ("GET", "/api/v1/sessions/stats"),
            ("GET", "/"),
        ]
        for method, path in endpoints:
            res = client.request(method, path)
            assert res.status_code == 200, f"{method} {path} failed: {res.status_code}"

        chat = client.post(
            "/api/v1/chat",
            json={"message": "smoke test", "session_id": session_id},
        )
        assert chat.status_code == 200
