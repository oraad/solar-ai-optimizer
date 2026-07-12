"""Persist MCP enable/token on the data volume (mcp.env)."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

MCP_ENV_FILENAME = "mcp.env"
_ENV_KEY_RE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")
_HEADER = "# MCP agent access — written by Settings; do not commit"


def mcp_env_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / MCP_ENV_FILENAME


def generate_mcp_token() -> str:
    """Cryptographically strong hex token (32 bytes)."""
    return secrets.token_hex(32)


def read_env_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ENV_KEY_RE.match(line.strip())
        if match and match.group(1) == key:
            return match.group(2)
    return None


def read_mcp_env(data_dir: Path | str) -> dict[str, str]:
    """Return MCP_ENABLED / MCP_TOKEN from mcp.env if present."""
    path = mcp_env_path(data_dir)
    out: dict[str, str] = {}
    enabled = read_env_value(path, "MCP_ENABLED")
    token = read_env_value(path, "MCP_TOKEN")
    if enabled is not None:
        out["MCP_ENABLED"] = enabled
    if token is not None:
        out["MCP_TOKEN"] = token
    return out


def write_mcp_env(
    path: Path,
    *,
    enabled: bool,
    token: str | None = None,
    clear_token: bool = False,
) -> None:
    """Upsert MCP_ENABLED / MCP_TOKEN in mcp.env (mode 0600).

    ``token=None`` and ``clear_token=False`` keeps any existing MCP_TOKEN.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_token = read_env_value(path, "MCP_TOKEN") or ""
    if clear_token:
        new_token = ""
    elif token is not None:
        new_token = token
    else:
        new_token = existing_token

    updates = {
        "MCP_ENABLED": "true" if enabled else "false",
        "MCP_TOKEN": new_token,
    }
    lines: list[str] = []
    seen: set[str] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _ENV_KEY_RE.match(line.strip())
            if match:
                key = match.group(1)
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                    continue
            lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    if not lines or not lines[0].startswith("#"):
        lines.insert(0, _HEADER)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
