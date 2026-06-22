"""OpenTelemetry tracing, Sentry error reporting, and structured observability."""

import time
from typing import Any

import structlog

from src.config import get_settings

logger = structlog.get_logger()


def setup_sentry() -> None:
    """Initialize Sentry SDK if DSN is configured."""
    dsn = get_settings().sentry_dsn
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.25)
        logger.info("sentry_initialized")
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
        lines.append(f'nexus_uptime_seconds{{service="nexus"}} {snap["uptime_seconds"]}')
        return "\n".join(lines) + "\n"


collector = MetricsCollector()
