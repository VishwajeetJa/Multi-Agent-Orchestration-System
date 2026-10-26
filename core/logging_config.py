"""
Structured logging configuration using structlog.
Produces JSON logs with trace IDs linking all steps of a single workflow.
"""
from __future__ import annotations
import logging
import sys
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON output with context variable support."""
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def bind_session(session_id: str, **extra) -> None:
    """Bind a session_id to the current log context (all logs in this scope get this field)."""
    bind_contextvars(session_id=session_id, **extra)


def clear_log_context() -> None:
    """Clear all bound log context variables."""
    clear_contextvars()


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger bound to a module name."""
    return structlog.get_logger(name)
