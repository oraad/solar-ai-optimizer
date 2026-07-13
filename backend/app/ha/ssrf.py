"""SSRF protection for outbound HA URL validation.

Blocks link-local (169.254.0.0/16, fe80::/10) including the AWS/GCP
instance-metadata endpoint (169.254.169.254) unconditionally.

When *allow_private* is False, also blocks RFC 1918 and loopback ranges, and
fails closed (raises) if the hostname cannot be resolved at all — an
unresolvable host cannot be proven safe. When *allow_private* is True (the
default for home-LAN installs, so a HA instance at e.g. 192.168.1.100 works
out of the box), an unresolvable hostname only logs a warning and proceeds,
since air-gapped/offline environments are expected in that mode.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

log = logging.getLogger("ha.ssrf")

# Always blocked regardless of allow_private.
_ALWAYS_BLOCKED: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("169.254.0.0/16"),        # link-local; includes metadata IPs
    ipaddress.ip_network("::ffff:169.254.0.0/112"), # IPv4-mapped link-local
    ipaddress.ip_network("fe80::/10"),              # IPv6 link-local
]

# Blocked only when allow_private=False.
_PRIVATE_RANGES: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),   # IPv6 ULA
]


def _addr_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_private: bool) -> bool:
    for net in _ALWAYS_BLOCKED:
        if addr in net:
            return True
    if not allow_private:
        for net in _PRIVATE_RANGES:
            if addr in net:
                return True
    return False


def _describe_block(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_private: bool) -> str:
    for net in _ALWAYS_BLOCKED:
        if addr in net:
            return (
                f"HA URL resolves to link-local/metadata address {addr} "
                "(169.254.0.0/16 and fe80::/10 are always blocked, including "
                "cloud metadata endpoints)."
            )
    if not allow_private:
        return (
            f"HA URL resolves to private/loopback address {addr}. "
            "Set HA_ALLOW_PRIVATE_URL=true to allow LAN addresses."
        )
    return f"HA URL resolves to blocked address {addr}."


def validate_ha_url(url: str, allow_private: bool = True) -> None:
    """Validate a HA base URL for SSRF risks.

    Raises ``ValueError`` with a user-friendly message when the URL is
    considered unsafe. When ``allow_private`` is True, resolution failures
    (e.g. air-gapped / offline environments) only log a warning and proceed.
    When ``allow_private`` is False, resolution failures raise instead —
    an unresolvable hostname cannot be proven to avoid private/loopback
    ranges, so strict mode fails closed.
    """
    cleaned = url.strip().rstrip("/")
    if not cleaned.startswith(("http://", "https://")):
        raise ValueError("HA URL must start with http:// or https://")

    parsed = urlparse(cleaned)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("HA URL must include a valid hostname")

    # Try direct IP parse first.
    try:
        addr = ipaddress.ip_address(hostname)
        _check_addr(addr, allow_private)
        return
    except ValueError:
        pass  # not a bare IP — resolve it

    # Resolve hostname → IPs.
    port = parsed.port or (443 if cleaned.startswith("https://") else 80)
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        resolved = list({info[4][0] for info in infos})
    except OSError as exc:
        if not allow_private:
            raise ValueError(
                f"Could not resolve HA hostname {hostname!r} to verify it is not "
                "a private/loopback address. Set HA_ALLOW_PRIVATE_URL=true if "
                "this is expected (e.g. offline/air-gapped LAN), or fix DNS."
            ) from exc
        log.warning(
            "Could not resolve HA hostname %r for SSRF check; proceeding without IP validation",
            hostname,
        )
        return

    for ip_str in resolved:
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        _check_addr(addr, allow_private)


def _check_addr(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_private: bool) -> None:
    if _addr_blocked(addr, allow_private):
        raise ValueError(_describe_block(addr, allow_private))
