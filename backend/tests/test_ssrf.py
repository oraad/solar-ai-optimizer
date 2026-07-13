"""Tests for SSRF URL validation (ha/ssrf.py)."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from app.ha.ssrf import validate_ha_url


# ---------------------------------------------------------------------------
# Link-local / metadata — always blocked
# ---------------------------------------------------------------------------

def test_blocks_aws_metadata_ip():
    with pytest.raises(ValueError, match="link-local"):
        validate_ha_url("http://169.254.169.254/latest/meta-data", allow_private=True)


def test_blocks_aws_metadata_https():
    with pytest.raises(ValueError, match="link-local"):
        validate_ha_url("https://169.254.169.254", allow_private=False)


def test_blocks_link_local_range():
    with pytest.raises(ValueError, match="link-local"):
        validate_ha_url("http://169.254.1.1:8123", allow_private=True)


def test_blocks_ipv6_link_local():
    with pytest.raises(ValueError, match="link-local"):
        validate_ha_url("http://[fe80::1]:8123", allow_private=True)


def test_blocks_ipv6_link_local_even_when_strict():
    with pytest.raises(ValueError, match="link-local"):
        validate_ha_url("http://[fe80::abcd:1234]:8123", allow_private=False)


def test_blocks_hostname_resolving_to_ipv6_link_local():
    fake_infos = [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("fe80::1", 80, 0, 0))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(ValueError, match="link-local"):
            validate_ha_url("http://evil6.internal:8123", allow_private=True)


# ---------------------------------------------------------------------------
# RFC 1918 — blocked only when allow_private=False
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://192.168.1.100:8123",
    "http://10.0.0.1:8123",
    "http://172.16.5.5:8123",
])
def test_allows_private_when_allow_private_true(url: str):
    # Should not raise — this is the default for home-LAN installs.
    validate_ha_url(url, allow_private=True)


@pytest.mark.parametrize("url", [
    "http://192.168.1.100:8123",
    "http://10.0.0.1:8123",
    "http://172.16.5.5:8123",
])
def test_blocks_private_when_allow_private_false(url: str):
    with pytest.raises(ValueError, match="private"):
        validate_ha_url(url, allow_private=False)


def test_blocks_loopback_when_allow_private_false():
    with pytest.raises(ValueError, match="private"):
        validate_ha_url("http://127.0.0.1:8123", allow_private=False)


def test_allows_loopback_when_allow_private_true():
    validate_ha_url("http://127.0.0.1:8123", allow_private=True)


# ---------------------------------------------------------------------------
# Public URLs — always allowed
# ---------------------------------------------------------------------------

def test_allows_public_https():
    # DNS may be unavailable in sandboxed test environments; mock resolution
    # to a public IP so this only exercises the SSRF address-range check.
    fake_infos = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("203.0.113.10", 443))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        validate_ha_url("https://myhome.duckdns.org:8123", allow_private=False)


def test_allows_public_http():
    fake_infos = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("203.0.113.10", 80))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        validate_ha_url("http://ha.example.com:8123", allow_private=False)


# ---------------------------------------------------------------------------
# Invalid URL format
# ---------------------------------------------------------------------------

def test_rejects_missing_scheme():
    with pytest.raises(ValueError, match="http"):
        validate_ha_url("homeassistant.local:8123")


def test_rejects_ftp_scheme():
    with pytest.raises(ValueError, match="http"):
        validate_ha_url("ftp://homeassistant.local")


# ---------------------------------------------------------------------------
# Hostname resolution failures — non-fatal (offline / air-gapped environments)
# ---------------------------------------------------------------------------

def test_unresolvable_hostname_does_not_raise(caplog):
    import logging
    with patch("socket.getaddrinfo", side_effect=OSError("no address")):
        with caplog.at_level(logging.WARNING, logger="ha.ssrf"):
            validate_ha_url("http://ha.local.invalid:8123", allow_private=True)
    assert any("SSRF check" in r.message or "without IP validation" in r.message for r in caplog.records)


def test_unresolvable_hostname_raises_when_strict():
    """allow_private=False must fail closed: an unresolvable host cannot be
    proven to avoid private/loopback ranges, so proceeding would be unsafe."""
    with patch("socket.getaddrinfo", side_effect=OSError("no address")):
        with pytest.raises(ValueError, match="resolve"):
            validate_ha_url("http://ha.local.invalid:8123", allow_private=False)


# ---------------------------------------------------------------------------
# Hostname that resolves to a blocked IP
# ---------------------------------------------------------------------------

def test_blocks_hostname_resolving_to_link_local():
    fake_infos = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 80))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(ValueError, match="link-local"):
            validate_ha_url("http://evil.internal:8123", allow_private=True)


def test_blocks_hostname_resolving_to_private_when_disallowed():
    fake_infos = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 80))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(ValueError, match="private"):
            validate_ha_url("http://internal.example.com:8123", allow_private=False)


def test_allows_hostname_resolving_to_private_when_allowed():
    fake_infos = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.50", 80))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        validate_ha_url("http://internal.example.com:8123", allow_private=True)
