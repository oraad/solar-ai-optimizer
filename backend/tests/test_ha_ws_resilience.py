"""Tests for HA WebSocket error classification, backoff, and circuit breaker."""

from __future__ import annotations

import pytest

from app.ha.client import (
    HAAuthInvalid,
    HAClient,
    HAError,
    WsErrorClass,
    classify_ws_error,
)


class _Fake403(Exception):
    status_code = 403

    def __str__(self) -> str:
        return "server rejected WebSocket connection: HTTP 403"


def test_classify_auth_invalid() -> None:
    assert classify_ws_error(HAAuthInvalid("WebSocket auth failed: {'type': 'auth_invalid'}")) == (
        WsErrorClass.AUTH_INVALID
    )
    assert classify_ws_error(HAError("WebSocket auth failed: auth_invalid")) == (
        WsErrorClass.AUTH_INVALID
    )


def test_classify_banned() -> None:
    assert classify_ws_error(_Fake403()) == WsErrorClass.BANNED_OR_FORBIDDEN
    assert (
        classify_ws_error(Exception("InvalidStatus: server rejected WebSocket connection: HTTP 403"))
        == WsErrorClass.BANNED_OR_FORBIDDEN
    )


def test_classify_transient() -> None:
    assert classify_ws_error(OSError("Connection refused")) == WsErrorClass.TRANSIENT
    assert classify_ws_error(HAError("Unexpected greeting")) == WsErrorClass.TRANSIENT


def test_auth_invalid_opens_circuit_after_two() -> None:
    client = HAClient("http://ha.local:8123", "token")
    d1 = client._record_failure(HAAuthInvalid("auth_invalid"))
    assert client.last_ws_error_class == WsErrorClass.AUTH_INVALID
    assert client.ws_circuit_open is False
    assert d1 == 5.0

    d2 = client._record_failure(HAAuthInvalid("auth_invalid"))
    assert client.ws_circuit_open is True
    assert d2 >= 300.0
    assert client.ws_diagnostics()["ha_ws_circuit_open"] is True
    assert client.ws_diagnostics()["ha_ws_error_class"] == "auth_invalid"


def test_banned_backoff_grows_and_opens_circuit() -> None:
    client = HAClient("http://ha.local:8123", "token")
    d1 = client._record_failure(_Fake403())
    assert d1 == 60.0
    assert client.ws_circuit_open is False

    d2 = client._record_failure(_Fake403())
    assert d2 == 120.0

    d3 = client._record_failure(_Fake403())
    assert client.ws_circuit_open is True
    assert d3 >= 300.0
    assert client.last_ws_error_class == WsErrorClass.BANNED_OR_FORBIDDEN


def test_transient_backoff_caps_at_60() -> None:
    client = HAClient("http://ha.local:8123", "token")
    delays = []
    for _ in range(8):
        delays.append(client._record_failure(OSError("down")))
    assert delays[0] == 5.0
    assert delays[-1] == 60.0
    assert client.ws_circuit_open is False


def test_request_retry_closes_circuit() -> None:
    client = HAClient("http://ha.local:8123", "token")
    client._record_failure(HAAuthInvalid("auth_invalid"))
    client._record_failure(HAAuthInvalid("auth_invalid"))
    assert client.ws_circuit_open is True
    client.request_retry()
    assert client.ws_circuit_open is False
    assert client.ws_backoff_seconds == 5.0


def test_record_success_resets() -> None:
    client = HAClient("http://ha.local:8123", "token")
    client._record_failure(_Fake403())
    client._record_success()
    assert client.last_ws_error_class == WsErrorClass.NONE
    assert client.last_ws_error is None
    assert client.ws_circuit_open is False
