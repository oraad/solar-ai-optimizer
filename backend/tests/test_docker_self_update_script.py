"""Tests for docker-self-update.sh and helper spawn."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app.api.system_update import (
    UPDATE_SCRIPT,
    _build_helper_argv,
    _current_container_image,
    _spawn_updater,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if not (REPO_ROOT / "scripts" / "docker-self-update.sh").is_file():
    REPO_ROOT = Path("/app")
UPDATE_SCRIPT_PATH = REPO_ROOT / "scripts" / "docker-self-update.sh"
PULL_PROGRESS_PATH = REPO_ROOT / "scripts" / "lib" / "pull-progress.sh"


def test_update_script_exists_with_core_guards():
    text = UPDATE_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "docker rename" in text
    assert "wait_healthy" in text
    assert "rolled back" in text
    assert "pull-progress.sh" in text
    assert "recreate_from_inspect.py" in text
    assert "recreate_container" in text
    assert "run_solar_container" in text
    assert "cleanup_old_images" in text
    assert "PREVIOUS_IMAGE_ID" in text
    assert "IMAGE_RETENTION" in text


def test_pull_progress_layer_parser():
    sample = (
        "abc123def456: Pulling fs layer\n"
        "abc123def456: Download complete\n"
        "fedcba987654: Pulling fs layer\n"
        "fedcba987654: Already exists\n"
    )
    env = os.environ.copy()
    env["PULL_STATE_DIR"] = "/tmp/solar-pull-test-state"
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{PULL_PROGRESS_PATH}" && pull_progress_from_lines',
        ],
        input=sample,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    pct = (result.stdout or "").strip()
    assert pct == "99"  # layer parser caps at 99 until pull command exits


def test_build_helper_argv_update(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SELF_UPDATE_ENV_FILE", "/opt/solar-ai-optimizer/solar.env")
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    argv = _build_helper_argv(
        settings,
        operation="update",
        helper_image="ghcr.io/oraad/solar-ai-optimizer:0.5.10",
        target_image="ghcr.io/oraad/solar-ai-optimizer:0.5.11",
        from_version="0.5.10",
        to_version="0.5.11",
    )
    joined = " ".join(argv)
    assert "docker:cli" not in joined
    assert UPDATE_SCRIPT in joined
    assert "--entrypoint" in argv
    assert argv[argv.index("--entrypoint") + 1] == UPDATE_SCRIPT
    assert "ghcr.io/oraad/solar-ai-optimizer:0.5.11" in joined
    assert "update" in argv
    assert "/var/run/docker.sock:/var/run/docker.sock" in joined
    assert f"{settings.self_update_data_volume}:{settings.self_update_data_path}" in joined
    assert "/opt/solar-ai-optimizer:/opt/solar-ai-optimizer:ro" in joined
    assert "TARGET_IMAGE=ghcr.io/oraad/solar-ai-optimizer:0.5.11" in joined
    assert "IMAGE_RETENTION=2" in joined


def test_build_helper_argv_restore(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    argv = _build_helper_argv(
        settings,
        operation="restore",
        helper_image="ghcr.io/oraad/solar-ai-optimizer:0.5.10",
        target_image="ghcr.io/oraad/solar-ai-optimizer:0.5.9",
        from_version="0.5.9",
        to_version="0.5.9",
        backup_name="pre-from-0.5.9-to-0.5.10-1.tar.gz",
    )
    assert "restore" in argv
    assert "BACKUP_NAME=pre-from-0.5.9-to-0.5.10-1.tar.gz" in " ".join(argv)


def test_current_container_image_mock(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = "ghcr.io/oraad/solar-ai-optimizer:0.5.10\n"

        return R()

    monkeypatch.setattr("app.api.system_update.subprocess.run", fake_run)
    monkeypatch.setenv("DATA_DIR", "/tmp")
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    image = _current_container_image(settings)
    assert image == "ghcr.io/oraad/solar-ai-optimizer:0.5.10"
    assert calls[0][:3] == ["docker", "inspect", "-f"]


def test_spawn_updater_uses_current_image_as_helper(monkeypatch, tmp_path):
    """Helper must start from the running image so target pull is progress-reported."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    current = "ghcr.io/oraad/solar-ai-optimizer:0.5.10"
    target = "ghcr.io/oraad/solar-ai-optimizer:0.5.11"
    captured: list[list[str]] = []

    monkeypatch.setattr(
        "app.api.system_update._current_container_image",
        lambda _s: current,
    )

    def fake_spawn(_settings, cmd, *, log_label):
        captured.append(cmd)

    monkeypatch.setattr("app.api.system_update._spawn_helper", fake_spawn)

    _spawn_updater(
        settings,
        target_image=target,
        from_version="0.5.10",
        to_version="0.5.11",
    )

    assert len(captured) == 1
    argv = captured[0]
    joined = " ".join(argv)
    # docker run … helper_image … (helper is last arg before operation, or the image before "update")
    assert current in argv
    assert target in joined
    assert "TARGET_IMAGE=" + target in joined
    # helper image is the run image (last non-flag positional before operation)
    assert argv[-2] == current
    assert argv[-1] == "update"
    assert target not in {argv[-2]}  # helper is not the target
