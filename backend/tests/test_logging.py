"""Structured JSON logging."""

from __future__ import annotations

import io
import json
import logging

from app.logging_setup import configure_logging, request_id_var


def test_json_log_format_emits_parseable_line():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    from app.logging_setup import JsonLogFormatter, RequestIdFilter

    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    token = request_id_var.set("req-abc")
    try:
        logging.getLogger("test").info("hello structured")
    finally:
        request_id_var.reset(token)

    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert payload["message"] == "hello structured"
    assert payload["request_id"] == "req-abc"
    assert "timestamp" in payload

    configure_logging("INFO", fmt="text")
