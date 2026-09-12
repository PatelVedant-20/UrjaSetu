"""Logging configuration.

Phase 0 keeps this deliberately small: one configured root handler, a
consistent line format, and a request-id context variable that the error
envelope and access logs share.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

from app.core.config import get_settings

# Set per request by RequestIDMiddleware; read by the error envelope so a client
# can quote `request_id` and we can find the matching log lines.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"


class _RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def configure_logging() -> None:
    """Install UrjaSetu's log handler on the root logger.

    Idempotent: calling it twice does not duplicate handlers or duplicate output.
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(_RequestIDFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn installs its own handlers; let them propagate to ours instead so
    # every line carries the request id.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
