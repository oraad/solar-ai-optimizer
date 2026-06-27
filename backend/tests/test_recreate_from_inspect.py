"""Unit tests for scripts/recreate_from_inspect.py (no live Docker)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if not (REPO_ROOT / "scripts" / "recreate_from_inspect.py").is_file():
    REPO_ROOT = Path("/app")
SCRIPT_PATH = REPO_ROOT / "scripts" / "recreate_from_inspect.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "recreate"


def _load_module():
    spec = importlib.util.spec_from_file_location("recreate_from_inspect", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_build_create_config_proxmox_style():
    mod = _load_module()
    container = _load_fixture("container_proxmox.json")
    old_image = _load_fixture("image_old.json")
    target = "ghcr.io/oraad/solar-ai-optimizer:0.5.12"

    config = mod.build_create_config(container, old_image, target)

    assert config["Image"] == target
    env = config.get("Env") or []
    assert "SHADOW_MODE=true" in env
    assert "SELF_UPDATE_ENABLED=true" in env
    assert f"SELF_UPDATE_IMAGE={target}" in env
    assert "PATH=/usr/local/bin:/usr/bin" not in env


def test_build_create_host_config_preserves_bindings():
    mod = _load_module()
    container = _load_fixture("container_compose_custom.json")

    host = mod.build_create_host_config(container)

    assert host["PortBindings"]["8000/tcp"][0]["HostPort"] == "9000"
    assert host["RestartPolicy"]["Name"] == "unless-stopped"
    binds = host.get("Binds") or []
    assert any("solar-data:/app/data" in b for b in binds)
    assert any("/host/config.yaml:/app/config/config.yaml:ro" in b for b in binds)


def test_build_create_config_clears_entrypoint_when_image_default():
    mod = _load_module()
    container = _load_fixture("container_compose_custom.json")
    old_image = _load_fixture("image_old.json")
    target = "ghcr.io/oraad/solar-ai-optimizer:0.5.12"

    config = mod.build_create_config(container, old_image, target)

    assert config.get("Entrypoint") is None
    assert config.get("Cmd") is None


def test_build_create_config_keeps_custom_healthcheck():
    mod = _load_module()
    container = _load_fixture("container_custom_health.json")
    old_image = _load_fixture("image_old.json")
    target = "ghcr.io/oraad/solar-ai-optimizer:0.5.12"

    config = mod.build_create_config(container, old_image, target)
    health = config.get("Healthcheck") or {}

    assert health.get("Test") == [
        "CMD-SHELL",
        "curl -fsS http://localhost:8000/api/health || exit 1",
    ]


def test_build_networking_config_strips_runtime_fields():
    mod = _load_module()
    container = _load_fixture("container_compose_custom.json")

    networking = mod.build_networking_config(container)
    endpoints = networking["EndpointsConfig"]

    assert "solar_default" in endpoints
    assert "IPAddress" not in endpoints["solar_default"]
    assert "NetworkID" not in endpoints["solar_default"]


def test_simple_network_config_single_endpoint():
    mod = _load_module()
    container = _load_fixture("container_compose_custom.json")
    networking = mod.build_networking_config(container)
    simple = mod._simple_network_config(networking)

    assert len(simple["EndpointsConfig"]) == 1
