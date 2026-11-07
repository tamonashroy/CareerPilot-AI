"""Structured JSON logging with a correlation ID on every line."""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"password|passwd|secret|token|api_?key|authorization|cookie|database_url|cv_text",
    re.IGNORECASE,
)
_URL_CREDENTIALS = re.compile(r"(\w+://[^:/@\s]+:)[^@\s]+@")
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys() | {"message", "asctime"}
)


def _redact(value: Any, key: str = "") -> Any:
    if key and _SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return _URL_CREDENTIALS.sub(rf"\1{REDACTED}@", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
            "correlation_id": correlation_id.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                entry[key] = _redact(value, key)
        if record.exc_info and record.exc_info[0] is not None:
            # The type only: exception messages and tracebacks can carry user data.
            entry["exception_type"] = record.exc_info[0].__name__
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Replaced by our own request log, which includes the correlation ID.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
