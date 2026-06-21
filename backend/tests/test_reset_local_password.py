"""Tests for local admin password reset."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from app.api.session import verify_local_password
from app.auth.local_credentials import (
    generate_password,
    hash_password,
    local_auth_env_path,
    read_env_value,
    write_local_auth_env,
)
from app.config import Settings
from scripts.reset_local_password import main as reset_main


def test_generate_password_length_and_charset():
    password = generate_password()
    assert len(password) == 24
    assert password.isalnum()


def test_write_local_auth_env_creates_file(tmp_path: Path):
    path = local_auth_env_path(tmp_path)
    write_local_auth_env(
        path,
        username="admin",
        password_hash="$2b$12$test",
        session_secret="abc123",
    )
    text = path.read_text(encoding="utf-8")
    assert "LOCAL_ADMIN_USERNAME=admin" in text
    assert "LOCAL_ADMIN_PASSWORD_HASH=$2b$12$test" in text
    assert "SESSION_SECRET=abc123" in text
    assert "LOCAL_ADMIN_PASSWORD=" not in text
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_write_local_auth_env_upserts_and_strips_plain_password(tmp_path: Path):
    path = local_auth_env_path(tmp_path)
    path.write_text(
        "LOCAL_ADMIN_USERNAME=old\n"
        "LOCAL_ADMIN_PASSWORD=plain\n"
        "LOCAL_ADMIN_PASSWORD_HASH=$2b$old\n"
        "SESSION_SECRET=oldsecret\n",
        encoding="utf-8",
    )
    write_local_auth_env(
        path,
        username="admin",
        password_hash="$2b$12$new",
        session_secret="newsecret",
    )
    text = path.read_text(encoding="utf-8")
    assert "LOCAL_ADMIN_PASSWORD=plain" not in text
    assert "LOCAL_ADMIN_PASSWORD_HASH=$2b$12$new" in text
    assert "SESSION_SECRET=newsecret" in text
    assert read_env_value(path, "LOCAL_ADMIN_USERNAME") == "admin"


def test_hash_verifies_with_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    password = "test-secret"
    password_hash = hash_password(password)
    path = local_auth_env_path(tmp_path)
    write_local_auth_env(
        path,
        username="admin",
        password_hash=password_hash,
        session_secret="sess",
    )
    monkeypatch.setenv("LOCAL_ADMIN_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("LOCAL_ADMIN_USERNAME", "admin")
    settings = Settings()
    assert verify_local_password(password, settings)


def test_reset_main_rotates_session_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_path = local_auth_env_path(tmp_path)
    env_path.write_text("SESSION_SECRET=keep-me\n", encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_main(["--password", "newpass", "--username", "admin"])
    assert read_env_value(env_path, "SESSION_SECRET") != "keep-me"


def test_reset_main_keep_sessions_preserves_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    env_path = local_auth_env_path(tmp_path)
    env_path.write_text("SESSION_SECRET=keep-me\n", encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_main(["--password", "newpass", "--keep-sessions"])
    assert read_env_value(env_path, "SESSION_SECRET") == "keep-me"


def test_reset_main_prints_machine_readable_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_main(["--password", "explicit", "--username", "ops"])
    out = capsys.readouterr().out
    assert "USERNAME=ops" in out
    assert "PASSWORD=explicit" in out
    assert f"ENV_FILE={local_auth_env_path(tmp_path)}" in out
