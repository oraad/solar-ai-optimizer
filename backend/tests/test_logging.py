"""Structured JSON logging."""

from __future__ import annotations

import io
import json
import logging

from app.logging_setup import ShieldedKeepaliveFilter, configure_logging, request_id_var


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


def test_shielded_keepalive_filter_downgrades_asyncio_error():
    filt = ShieldedKeepaliveFilter()
    record = logging.LogRecord(
        name="asyncio",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg=(
            "ConnectionClosedError exception in shielded future "
            "keepalive ping timeout"
        ),
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert record.levelno == logging.DEBUG
    assert record.levelname == "DEBUG"
