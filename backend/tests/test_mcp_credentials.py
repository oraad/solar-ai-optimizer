"""mcp.env persistence helpers."""

from __future__ import annotations

from pathlib import Path

from app.mcp.credentials import (
    generate_mcp_token,
    mcp_env_path,
    read_mcp_env,
    write_mcp_env,
)


def test_generate_mcp_token_hex_length():
    token = generate_mcp_token()
    assert len(token) == 64
    int(token, 16)


def test_write_and_read_mcp_env(tmp_path: Path):
    path = mcp_env_path(tmp_path)
    write_mcp_env(path, enabled=True, token="secret-one")
    data = read_mcp_env(tmp_path)
    assert data["MCP_ENABLED"] == "true"
    assert data["MCP_TOKEN"] == "secret-one"

    write_mcp_env(path, enabled=False, token=None)
    data = read_mcp_env(tmp_path)
    assert data["MCP_ENABLED"] == "false"
    assert data["MCP_TOKEN"] == "secret-one"

    write_mcp_env(path, enabled=True, clear_token=True)
    data = read_mcp_env(tmp_path)
    assert data["MCP_ENABLED"] == "true"
    assert data["MCP_TOKEN"] == ""
