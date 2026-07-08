"""Paired API clients (HA integration) and one-time pairing codes."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("auth.api_clients")

CLIENTS_FILENAME = "api_clients.json"
CODE_TTL_SECONDS = 600
CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford (no ILOU)
TOKEN_PREFIX = "sol_c_"
GENERATE_MAX_PER_HOUR = 10
REDEEM_MAX_PER_WINDOW = 5
REDEEM_WINDOW_SECONDS = 300
REDEEM_BURN_AFTER_FAILS = 10

_lock = threading.RLock()
_generate_times: list[float] = []
_redeem_fails: dict[str, list[float]] = {}


@dataclass(frozen=True)
class PairedClient:
    id: str
    token_hash: str
    name: str
    created_at: str
    last_used_at: str | None = None


def clients_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / CLIENTS_FILENAME


def normalize_pairing_code(code: str) -> str:
    cleaned = (
        code.strip()
        .upper()
        .replace("-", "")
        .replace(" ", "")
        .replace("O", "0")
        .replace("I", "1")
        .replace("L", "1")
    )
    return cleaned


def format_pairing_code(normalized: str) -> str:
    if len(normalized) != 8:
        return normalized
    return f"{normalized[:4]}-{normalized[4:]}"


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _read_store(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"pending": None, "clients": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("Corrupt api_clients store at %s; resetting pending", path)
        return {"pending": None, "clients": []}
    if not isinstance(data, dict):
        return {"pending": None, "clients": []}
    clients = data.get("clients")
    if not isinstance(clients, list):
        clients = []
    last_redeemed = data.get("last_redeemed")
    out: dict[str, Any] = {"pending": data.get("pending"), "clients": clients}
    if isinstance(last_redeemed, dict):
        out["last_redeemed"] = last_redeemed
    return out


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def has_paired_clients(data_dir: Path | str) -> bool:
    store = _read_store(clients_path(data_dir))
    return any(isinstance(c, dict) and c.get("token_hash") for c in store["clients"])


def list_clients(data_dir: Path | str) -> list[dict[str, Any]]:
    store = _read_store(clients_path(data_dir))
    out: list[dict[str, Any]] = []
    for raw in store["clients"]:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        out.append(
            {
                "id": raw["id"],
                "name": raw.get("name") or "Client",
                "created_at": raw.get("created_at"),
                "last_used_at": raw.get("last_used_at"),
            }
        )
    return out


def pending_status(data_dir: Path | str) -> dict[str, Any] | None:
    with _lock:
        path = clients_path(data_dir)
        store = _read_store(path)
        pending = store.get("pending")
        if not isinstance(pending, dict):
            return None
        expires_raw = pending.get("expires_at")
        try:
            expires = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
        except ValueError:
            store["pending"] = None
            _atomic_write(path, store)
            return None
        if expires <= _utc_now():
            store["pending"] = None
            _atomic_write(path, store)
            return None
        return {
            "expires_at": _iso(expires),
            "expires_in": max(0, int((expires - _utc_now()).total_seconds())),
            "created_by": pending.get("created_by"),
        }


def _allow_generate() -> bool:
    now = time.monotonic()
    cutoff = now - 3600
    while _generate_times and _generate_times[0] < cutoff:
        _generate_times.pop(0)
    if len(_generate_times) >= GENERATE_MAX_PER_HOUR:
        return False
    _generate_times.append(now)
    return True


def start_pairing(
    data_dir: Path | str,
    *,
    created_by: str | None = None,
) -> dict[str, Any]:
    with _lock:
        if not _allow_generate():
            raise PairingError("rate_limited", 429)
        path = clients_path(data_dir)
        store = _read_store(path)
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        expires = _utc_now() + timedelta(seconds=CODE_TTL_SECONDS)
        store["pending"] = {
            "code_hash": _hash_secret(raw),
            "expires_at": _iso(expires),
            "created_by": created_by,
            "fail_count": 0,
        }
        _atomic_write(path, store)
        display = format_pairing_code(raw)
        log.info("Pairing code issued (expires in %ss)", CODE_TTL_SECONDS)
        return {
            "code": display,
            "expires_at": _iso(expires),
            "expires_in": CODE_TTL_SECONDS,
        }


def cancel_pairing(data_dir: Path | str) -> None:
    with _lock:
        path = clients_path(data_dir)
        store = _read_store(path)
        store["pending"] = None
        _atomic_write(path, store)


def _redeem_rate_ok(client_ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - REDEEM_WINDOW_SECONDS
    fails = [t for t in _redeem_fails.get(client_ip, []) if t >= cutoff]
    _redeem_fails[client_ip] = fails
    return len(fails) < REDEEM_MAX_PER_WINDOW


def _record_redeem_fail(client_ip: str) -> None:
    _redeem_fails.setdefault(client_ip, []).append(time.monotonic())


def redeem_pairing(
    data_dir: Path | str,
    *,
    code: str,
    client_name: str,
    client_ip: str = "",
) -> dict[str, Any]:
    with _lock:
        if client_ip and not _redeem_rate_ok(client_ip):
            raise PairingError("rate_limited", 429)
        path = clients_path(data_dir)
        store = _read_store(path)
        pending = store.get("pending")
        if not isinstance(pending, dict):
            if client_ip:
                _record_redeem_fail(client_ip)
            last = store.get("last_redeemed")
            if isinstance(last, dict) and last.get("code_hash"):
                normalized = normalize_pairing_code(code)
                given = _hash_secret(normalized)
                if hmac.compare_digest(given, str(last["code_hash"])):
                    try:
                        redeemed_at = datetime.fromisoformat(
                            str(last.get("redeemed_at")).replace("Z", "+00:00")
                        )
                        if (_utc_now() - redeemed_at).total_seconds() < 120:
                            raise PairingError("conflict", 409)
                    except ValueError:
                        pass
            raise PairingError("invalid_or_expired", 400)

        expires_raw = pending.get("expires_at")
        try:
            expires = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
        except ValueError:
            store["pending"] = None
            _atomic_write(path, store)
            raise PairingError("invalid_or_expired", 400) from None
        if expires <= _utc_now():
            store["pending"] = None
            _atomic_write(path, store)
            raise PairingError("invalid_or_expired", 400)

        normalized = normalize_pairing_code(code)
        expected = str(pending.get("code_hash") or "")
        given = _hash_secret(normalized)
        if not expected or not hmac.compare_digest(given, expected):
            fails = int(pending.get("fail_count") or 0) + 1
            pending["fail_count"] = fails
            if fails >= REDEEM_BURN_AFTER_FAILS:
                store["pending"] = None
            else:
                store["pending"] = pending
            _atomic_write(path, store)
            if client_ip:
                _record_redeem_fail(client_ip)
            raise PairingError("invalid_or_expired", 400)

        # Single-flight: clear pending before minting so concurrent redeem loses.
        store["pending"] = None
        store["last_redeemed"] = {
            "code_hash": expected,
            "redeemed_at": _iso(_utc_now()),
        }
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        client_id = str(secrets.token_hex(16))
        now = _iso(_utc_now())
        name = (client_name or "Home Assistant").strip()[:128] or "Home Assistant"
        store["clients"].append(
            {
                "id": client_id,
                "token_hash": _hash_secret(token),
                "name": name,
                "created_at": now,
                "last_used_at": None,
            }
        )
        _atomic_write(path, store)
        return {
            "client_id": client_id,
            "access_token": token,
            "token_type": "Bearer",
            "name": name,
        }


def revoke_client(data_dir: Path | str, client_id: str) -> bool:
    with _lock:
        path = clients_path(data_dir)
        store = _read_store(path)
        before = len(store["clients"])
        store["clients"] = [
            c
            for c in store["clients"]
            if not (isinstance(c, dict) and c.get("id") == client_id)
        ]
        if len(store["clients"]) == before:
            return False
        _atomic_write(path, store)
        return True


def match_client_token(
    data_dir: Path | str, provided: str
) -> PairedClient | None:
    if not provided.startswith(TOKEN_PREFIX):
        return None
    digest = _hash_secret(provided)
    path = clients_path(data_dir)
    with _lock:
        store = _read_store(path)
        for raw in store["clients"]:
            if not isinstance(raw, dict):
                continue
            token_hash = raw.get("token_hash")
            if not isinstance(token_hash, str):
                continue
            if hmac.compare_digest(digest, token_hash):
                client = PairedClient(
                    id=str(raw.get("id") or ""),
                    token_hash=token_hash,
                    name=str(raw.get("name") or "Client"),
                    created_at=str(raw.get("created_at") or ""),
                    last_used_at=raw.get("last_used_at"),
                )
                # Best-effort last_used update
                raw["last_used_at"] = _iso(_utc_now())
                try:
                    _atomic_write(path, store)
                except OSError:
                    pass
                return client
    return None


class PairingError(Exception):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
