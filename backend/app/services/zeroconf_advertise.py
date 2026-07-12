"""mDNS / Zeroconf advertisement for standalone Solar instances."""

from __future__ import annotations

import logging
import socket
from typing import Any

from ..auth.install_id import get_or_create_install_id
from ..config import Settings

log = logging.getLogger("services.zeroconf_advertise")

SERVICE_TYPE = "_solar-ai._tcp.local."
DEFAULT_PORT = 8000


def _lan_ipv4() -> str:
    """Best-effort primary LAN address for advertisement."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class ZeroconfAdvertiser:
    """Advertise ``_solar-ai._tcp.local.`` while the process is running."""

    def __init__(self) -> None:
        self._zc: Any = None
        self._info: Any = None

    def start(self, settings: Settings) -> None:
        if settings.is_addon:
            return
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            log.warning("zeroconf package not installed; skipping mDNS advertisement")
            return

        install_id = get_or_create_install_id(settings.data_dir)
        host = _lan_ipv4()
        try:
            addresses = [socket.inet_aton(host)]
        except OSError:
            addresses = [socket.inet_aton("127.0.0.1")]

        name = f"Solar AI Optimizer.{SERVICE_TYPE}"
        try:
            info = ServiceInfo(
                SERVICE_TYPE,
                name,
                addresses=addresses,
                port=DEFAULT_PORT,
                properties={"install_id": install_id.encode("utf-8")},
                server=f"solar-ai-{install_id[:8]}.local.",
            )
            zc = Zeroconf()
            zc.register_service(info)
        except Exception as exc:  # noqa: BLE001
            log.warning("Zeroconf advertisement failed: %s", exc)
            return

        self._zc = zc
        self._info = info
        log.info(
            "Advertising zeroconf %s on %s:%s install_id=%s",
            SERVICE_TYPE,
            host,
            DEFAULT_PORT,
            install_id,
        )

    def stop(self) -> None:
        if self._zc is None:
            return
        try:
            if self._info is not None:
                self._zc.unregister_service(self._info)
            self._zc.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("Zeroconf shutdown failed: %s", exc)
        finally:
            self._zc = None
            self._info = None
