"""OpenTelemetry tracing, Sentry error reporting, and structured observability."""

import time
from typing import Any

import structlog

from src.config import get_settings

logger = structlog.get_logger()


def setup_sentry() -> None:
    """Initialize Sentry SDK if DSN is configured."""
    settings = get_settings()
    dsn = settings.sentry_dsn
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=settings.app_env or "development",
            traces_sample_rate=0.25,
            integrations=[StarletteIntegration(), FastApiIntegration()],
        )
        logger.info("sentry_initialized", environment=settings.app_env)
    except Exception as e:
        logger.warning("sentry_init_failed", error=str(e))


def setup_opentelemetry() -> None:
    """Initialize OpenTelemetry if endpoint is configured."""
    endpoint = get_settings().otel_endpoint
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({SERVICE_NAME: "nexus-voice-agents"})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("opentelemetry_initialized", endpoint=endpoint)
    except Exception as e:
        logger.warning("opentelemetry_init_failed", error=str(e))


class MetricsCollector:
    """Collects and exposes custom application metrics."""

    def __init__(self):
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._started_at = time.time()

    def increment(self, name: str, value: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + value

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        if name not in self._histograms:
            self._histograms[name] = []
        self._histograms[name].append(value)
        if len(self._histograms[name]) > 1000:
            self._histograms[name] = self._histograms[name][-500:]

    def snapshot(self) -> dict[str, Any]:
        hist_summary = {}
        for name, vals in self._histograms.items():
            if vals:
                hist_summary[name] = {
                    "count": len(vals),
                    "avg": round(sum(vals) / len(vals), 2),
                    "min": round(min(vals), 2),
                    "max": round(max(vals), 2),
                    "p50": round(sorted(vals)[len(vals) // 2], 2),
                    "p95": round(sorted(vals)[int(len(vals) * 0.95)], 2) if len(vals) > 1 else vals[0],
                }

        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": hist_summary,
            "uptime_seconds": round(time.time() - self._started_at),
        }

    def prometheus_text(self) -> str:
        snap = self.snapshot()
        lines = []
        for name, val in snap["counters"].items():
            lines.append(f"# HELP nexus_{name} Counter metric")
            lines.append(f"# TYPE nexus_{name} counter")
            lines.append(f'nexus_{name}{{service="nexus"}} {val}')
        for name, val in snap["gauges"].items():
            lines.append(f"# HELP nexus_{name} Gauge metric")
            lines.append(f"# TYPE nexus_{name} gauge")
            lines.append(f'nexus_{name}{{service="nexus"}} {val}')
        for name, summary in snap["histograms"].items():
            lines.append(f"# HELP nexus_{name} Request latency histogram")
            lines.append(f"# TYPE nexus_{name} gauge")
            lines.append(f'nexus_{name}_count{{service="nexus"}} {summary["count"]}')
            lines.append(f'nexus_{name}_avg{{service="nexus"}} {summary["avg"]}')
            lines.append(f'nexus_{name}_p95{{service="nexus"}} {summary["p95"]}')
        lines.append(f'nexus_uptime_seconds{{service="nexus"}} {snap["uptime_seconds"]}')
        return "\n".join(lines) + "\n"


class ActiveGauge:
    """Single consolidated gauge tracking active requests, tasks, and sessions."""

    def __init__(self):
        self._active_requests = 0
        self._active_tasks = 0
        self._active_sessions = 0
        self._peak_requests = 0
        self._peak_tasks = 0

    def incr_requests(self) -> None:
        self._active_requests += 1
        if self._active_requests > self._peak_requests:
            self._peak_requests = self._active_requests

    def decr_requests(self) -> None:
        if self._active_requests > 0:
            self._active_requests -= 1

    def incr_tasks(self) -> None:
        self._active_tasks += 1
        if self._active_tasks > self._peak_tasks:
            self._peak_tasks = self._active_tasks

    def decr_tasks(self) -> None:
        if self._active_tasks > 0:
            self._active_tasks -= 1

    def set_sessions(self, count: int) -> None:
        self._active_sessions = count

    def snapshot(self) -> dict[str, int]:
        return {
            "active_requests": self._active_requests,
            "active_tasks": self._active_tasks,
            "active_sessions": self._active_sessions,
            "peak_requests": self._peak_requests,
            "peak_tasks": self._peak_tasks,
        }

    def prometheus_text(self) -> str:
        snap = self.snapshot()
        return (
            "# HELP nexus_active_requests Currently active HTTP requests\n"
            "# TYPE nexus_active_requests gauge\n"
            f'nexus_active_requests{{service="nexus"}} {snap["active_requests"]}\n'
            "# HELP nexus_active_tasks Currently active background tasks\n"
            "# TYPE nexus_active_tasks gauge\n"
            f'nexus_active_tasks{{service="nexus"}} {snap["active_tasks"]}\n'
            "# HELP nexus_active_sessions Currently active voice/sessions\n"
            "# TYPE nexus_active_sessions gauge\n"
            f'nexus_active_sessions{{service="nexus"}} {snap["active_sessions"]}\n'
        )


collector = MetricsCollector()
active_gauge = ActiveGauge()
