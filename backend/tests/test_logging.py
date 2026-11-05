import json
import logging
import sys

from app.core.logging import JsonFormatter, correlation_id


def _format(message: str, *args: object, exc_info: object = None, **extra: object) -> dict:
    record = logging.LogRecord("test", logging.INFO, "f.py", 1, message, args, exc_info)  # type: ignore[arg-type]
    record.__dict__.update(extra)
    return json.loads(JsonFormatter().format(record))


def test_has_the_standard_fields() -> None:
    entry = _format("hello %s", "world", job_id="j1")
    assert entry["message"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "test"
    assert entry["timestamp"]
    assert entry["job_id"] == "j1"


def test_includes_the_correlation_id() -> None:
    token = correlation_id.set("req-1")
    try:
        assert _format("x")["correlation_id"] == "req-1"
    finally:
        correlation_id.reset(token)


def test_redacts_sensitive_fields_at_any_depth() -> None:
    entry = _format(
        "x",
        password="p1",
        api_key="k1",
        cv_text="my whole cv",
        context={"session_token": "t1", "safe": "visible"},
    )
    text = json.dumps(entry)
    for secret in ("p1", "k1", "my whole cv", "t1"):
        assert secret not in text
    assert entry["context"]["safe"] == "visible"


def test_redacts_credentials_inside_urls() -> None:
    entry = _format("connecting to postgresql://user:hunter2@db/app")
    assert "hunter2" not in entry["message"]
    assert "user" in entry["message"]


def test_logs_exception_type_but_not_its_message() -> None:
    try:
        raise ValueError("full cv text here")
    except ValueError:
        entry = _format("failed", exc_info=sys.exc_info())
    assert entry["exception_type"] == "ValueError"
    assert "full cv text" not in json.dumps(entry)
