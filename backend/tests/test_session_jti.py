"""Tests for JTI revocation in session cookies."""

from __future__ import annotations

import time

import pytest

from app.api.session import (
    _REVOKED_JTIS,
    _decode_cookie,
    _is_jti_revoked,
    make_session_cookie,
    parse_local_cookie,
    revoke_jti,
)
from app.config import Settings


def _settings(**kwargs) -> Settings:
    return Settings(
        ha_token="",
        database_url="sqlite+aiosqlite:///:memory:",
        session_secret="test-secret-32-chars-long-enough",
        **kwargs,
    )


def _request_with_cookie(cookie_value: str):
    """Build a minimal Starlette Request carrying the given cookie."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/status",
        "headers": [(b"cookie", f"solar_session={cookie_value}".encode())],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Cookie contains jti
# ---------------------------------------------------------------------------

def test_make_session_cookie_includes_jti():
    settings = _settings()
    token = make_session_cookie("admin", settings)
    payload = _decode_cookie(token, settings)
    assert payload is not None
    assert "jti" in payload
    assert isinstance(payload["jti"], str)
    assert len(payload["jti"]) > 8


def test_jti_is_unique_across_mints():
    settings = _settings()
    t1 = make_session_cookie("admin", settings)
    t2 = make_session_cookie("admin", settings)
    p1 = _decode_cookie(t1, settings)
    p2 = _decode_cookie(t2, settings)
    assert p1 is not None and p2 is not None
    assert p1["jti"] != p2["jti"]


# ---------------------------------------------------------------------------
# Revocation set
# ---------------------------------------------------------------------------

def test_revoke_jti_rejects_cookie():
    settings = _settings()
    token = make_session_cookie("admin", settings)
    payload = _decode_cookie(token, settings)
    assert payload is not None

    jti = payload["jti"]
    exp = payload["exp"]
    revoke_jti(jti, float(exp))

    # Cookie should now decode to None.
    assert _decode_cookie(token, settings) is None


def test_unrevoked_cookie_still_valid():
    settings = _settings()
    token = make_session_cookie("admin", settings)
    payload = _decode_cookie(token, settings)
    assert payload is not None


def test_is_jti_revoked_false_before_revoke():
    assert _is_jti_revoked("nonexistent-jti-xyz") is False


def test_is_jti_revoked_true_after_revoke():
    jti = "test-jti-12345"
    exp = time.time() + 3600
    revoke_jti(jti, exp)
    assert _is_jti_revoked(jti) is True


def test_revoke_jti_purges_expired_entries():
    # Add an already-expired entry first.
    stale_jti = "stale-jti-expired"
    revoke_jti(stale_jti, time.time() - 1)  # already expired

    fresh_jti = "fresh-jti-live"
    revoke_jti(fresh_jti, time.time() + 3600)  # not expired

    # stale_jti should have been purged by the fresh write.
    assert _is_jti_revoked(stale_jti) is False
    assert _is_jti_revoked(fresh_jti) is True


def test_parse_local_cookie_rejects_revoked():
    settings = _settings(local_admin_username="admin")
    token = make_session_cookie("admin", settings)

    req_ok = _request_with_cookie(token)
    assert parse_local_cookie(req_ok, settings) is not None

    # Revoke the jti.
    payload = _decode_cookie(token, settings)
    assert payload is not None
    revoke_jti(payload["jti"], float(payload["exp"]))

    req_revoked = _request_with_cookie(token)
    assert parse_local_cookie(req_revoked, settings) is None


# ---------------------------------------------------------------------------
# Default session TTL changed to 12 h
# ---------------------------------------------------------------------------

def test_default_session_ttl_is_12h():
    settings = _settings()
    assert settings.session_ttl_hours == 12


def test_session_cookie_expires_in_12h_by_default():
    settings = _settings()
    token = make_session_cookie("admin", settings)
    payload = _decode_cookie(token, settings)
    assert payload is not None
    ttl = payload["exp"] - payload["iat"]
    assert ttl == 12 * 3600
