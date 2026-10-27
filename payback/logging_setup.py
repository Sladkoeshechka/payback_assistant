"""Structured JSON logging.

Two things on top of a plain formatter:

* every record carries whatever context is bound around it — ``expense_id`` and
  ``planfix_task_id`` — so one expense can be followed across the bot, the Planfix
  client and the webhook handler;
* values registered with :func:`redact` are masked in the rendered line, so a token
  cannot reach the log through an exception message or a stray repr.
"""

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_EMPTY: dict[str, Any] = {}
_context: ContextVar[dict[str, Any]] = ContextVar("payback_log_context", default=_EMPTY)
_secrets: set[str] = set()

_MIN_SECRET_LENGTH = 8
"""Shorter values are too likely to occur in ordinary text to mask blindly."""

_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
    | {"message", "asctime", "taskName"}
)


def redact(*values: str | None) -> None:
    """Register secret values to be masked in log output."""
    for value in values:
        if value and len(value) >= _MIN_SECRET_LENGTH:
            _secrets.add(value)


def clear_redactions() -> None:
    """Drop every registered secret. For tests."""
    _secrets.clear()


@contextmanager
def log_context(**values: Any) -> Iterator[None]:
    """Bind fields onto every record emitted inside the block."""
    token = _context.set({**_context.get(), **values})
    try:
        yield
    finally:
        _context.reset(token)


class JsonFormatter(logging.Formatter):
    """Renders one JSON object per record, with secrets masked."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_context.get())
        # Fields passed as logger.info("...", extra={"expense_id": 1}).
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _RESERVED and not key.startswith("_")
            }
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        rendered = json.dumps(payload, ensure_ascii=False, default=str)
        for secret in _secrets:
            rendered = rendered.replace(secret, "***")
        return rendered


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # aiogram and httpx log every update and request at INFO; one notch quieter.
    for noisy in ("aiogram.event", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


__all__ = [
    "JsonFormatter",
    "clear_redactions",
    "configure_logging",
    "log_context",
    "redact",
]
