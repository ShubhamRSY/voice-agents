"""Structured logging setup with file and Loki sinks."""

import logging
import sys

import structlog

from src.config import ROOT_DIR, get_settings


def setup_logging() -> None:
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    sink = settings.log_sink

    # Common processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if sink == "file":
        log_path = ROOT_DIR / settings.log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=open(log_path, "a")),
        )
        _setup_file_rotation(str(log_path))

    elif sink == "loki" and settings.loki_url:
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        )
        _setup_loki_push(settings.loki_url)

    else:
        # Default: pretty console output (dev-friendly)
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        )


def _setup_file_rotation(log_path: str) -> None:
    """Configure log rotation via a simple size-based scheme."""
    try:
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(log_path, maxBytes=100 * 1024 * 1024, backupCount=5)
        handler.setFormatter(logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}'
        ))
        root = logging.getLogger()
        root.addHandler(handler)
    except Exception as exc:
        print(f"log_rotation_setup_failed: {exc}", file=sys.stderr)


def _setup_loki_push(loki_url: str) -> None:
    """Push logs to Loki via a simple background task."""
    try:
        import logging_loki
        handler = logging_loki.LokiHandler(
            url=f"{loki_url}/loki/api/v1/push",
            tags={"service": "nexus"},
            version="1",
        )
        root = logging.getLogger()
        root.addHandler(handler)
    except ImportError:
        pass
    except Exception as exc:
        print(f"loki_setup_failed: {exc}", file=sys.stderr)
