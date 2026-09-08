"""Process-wide logging setup with optional structured JSON output and
request/correlation IDs (Prompt 40 §25, §26).

A correlation id is stored in a ContextVar set by the API middleware and injected
into every log record. Set ``LOG_FORMAT=json`` for structured logs. Secrets are
never logged; a defensive redactor scrubs common token shapes from messages.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar

from config.settings import get_settings

DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [%(request_id)s] %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S"

# Correlation id for the current request/workflow (set by middleware / tasks).
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

# Defensive redaction of accidental secret leakage in log messages.
_REDACTORS = [
    re.compile(r"(sk-[A-Za-z0-9]{6})[A-Za-z0-9]{6,}"),
    re.compile(r"(AKIA)[0-9A-Z]{12,}"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE),
    re.compile(r"(xox[baprs]-)[0-9A-Za-z-]{6,}"),
]


def set_request_id(value: str) -> object:
    return _request_id.set(value)


def reset_request_id(token: object) -> None:
    try:
        _request_id.reset(token)  # type: ignore[arg-type]
    except (ValueError, LookupError):
        pass


def get_request_id() -> str:
    return _request_id.get()


def _redact(text: str) -> str:
    for pat in _REDACTORS:
        text = pat.sub(r"\1***", text)
    return text


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = _request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, DEFAULT_DATEFMT),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", _request_id.get()),
            "message": _redact(record.getMessage()),
        }
        # Merge structured extras (anything not a standard LogRecord attribute).
        for key, value in record.__dict__.items():
            if key in _STD_ATTRS or key in payload:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = str(value)
        if record.exc_info:
            payload["exc_info"] = _redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class TextRedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _redact(super().format(record))


_STD_ATTRS = set(vars(logging.makeLogRecord({})).keys()) | {"request_id", "message", "asctime"}


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once for API, pipeline, and CLI usage."""
    settings = get_settings()
    resolved = (level or settings.log_level).upper()
    numeric = getattr(logging, resolved, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if (settings.log_format or "text").lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextRedactingFormatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATEFMT))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(numeric)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
