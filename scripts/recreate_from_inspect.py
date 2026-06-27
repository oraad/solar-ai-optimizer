#!/usr/bin/env python3
"""Recreate a Docker container from inspect data (Watchtower-style).

Uses the Docker HTTP API over the Unix socket. Preserves runtime overrides
(ports, volumes, networks, env) while swapping the image reference.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.parse
from http.client import HTTPConnection
from typing import Any


DEFAULT_SOCKET = "/var/run/docker.sock"
API_VERSION = "v1.41"


class DockerError(Exception):
    """Docker API request failed."""


class DockerClient:
    def __init__(self, socket_path: str = DEFAULT_SOCKET) -> None:
        self.socket_path = socket_path

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        conn = HTTPConnection("localhost")
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.connect(self.socket_path)

        headers = {"Content-Type": "application/json"}
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()

        if response.status >= 400:
            detail = raw.decode("utf-8", errors="replace")
            raise DockerError(f"{method} {path} -> {response.status}: {detail}")

        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def container_inspect(self, name: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(name, safe="")
        return self._request("GET", f"/{API_VERSION}/containers/{encoded}/json")

    def image_inspect(self, ref: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(ref, safe="")
        return self._request("GET", f"/{API_VERSION}/images/{encoded}/json")

    def container_create(
        self,
        name: str,
        config: dict[str, Any],
        host_config: dict[str, Any],
        networking_config: dict[str, Any] | None,
    ) -> str:
        query = urllib.parse.urlencode({"name": name})
        body: dict[str, Any] = {**config, "HostConfig": host_config}
        if networking_config:
            body["NetworkingConfig"] = networking_config
        result = self._request("POST", f"/{API_VERSION}/containers/create?{query}", body)
        assert isinstance(result, dict)
        container_id = result.get("Id")
        if not container_id:
            raise DockerError("container create returned no Id")
        return str(container_id)

    def container_start(self, container_id: str) -> None:
        encoded = urllib.parse.quote(container_id, safe="")
        self._request("POST", f"/{API_VERSION}/containers/{encoded}/start", {})

    def network_disconnect(self, network: str, container_id: str, force: bool = True) -> None:
        net = urllib.parse.quote(network, safe="")
        self._request(
            "POST",
            f"/{API_VERSION}/networks/{net}/disconnect",
            {"Container": container_id, "Force": force},
        )

    def network_connect(
        self,
        network: str,
        container_id: str,
        endpoint: dict[str, Any] | None = None,
    ) -> None:
        net = urllib.parse.quote(network, safe="")
        body: dict[str, Any] = {"Container": container_id}
        if endpoint:
            body["EndpointConfig"] = endpoint
        self._request("POST", f"/{API_VERSION}/networks/{net}/connect", body)


def _slice_equal(a: Any, b: Any) -> bool:
    return a == b


def _slice_subtract(container_items: list[str] | None, image_items: list[str] | None) -> list[str]:
    image_set = set(image_items or [])
    return [item for item in (container_items or []) if item not in image_set]


def _string_map_subtract(
    container_map: dict[str, str] | None,
    image_map: dict[str, str] | None,
) -> dict[str, str]:
    image_map = image_map or {}
    result: dict[str, str] = {}
    for key, value in (container_map or {}).items():
        if image_map.get(key) != value:
            result[key] = value
    return result


def _struct_map_subtract(
    container_map: dict[str, Any] | None,
    image_map: dict[str, Any] | None,
) -> dict[str, Any]:
    image_map = image_map or {}
    return {k: v for k, v in (container_map or {}).items() if k not in image_map}


def _network_mode_is_container(host_config: dict[str, Any]) -> bool:
    mode = host_config.get("NetworkMode") or ""
    return isinstance(mode, str) and mode.startswith("container:")


def _patch_env(env: list[str] | None, updates: dict[str, str]) -> list[str]:
    current = list(env or [])
    keys = set(updates)
    patched = [entry for entry in current if entry.split("=", 1)[0] not in keys]
    for key, value in updates.items():
        patched.append(f"{key}={value}")
    return patched


def build_create_config(
    container_info: dict[str, Any],
    old_image_info: dict[str, Any],
    target_image: str,
) -> dict[str, Any]:
    """Build container Config for create API (Watchtower GetCreateConfig semantics)."""
    config = dict(container_info.get("Config") or {})
    host_config = container_info.get("HostConfig") or {}
    image_config = old_image_info.get("Config") or {}

    if config.get("WorkingDir") == image_config.get("WorkingDir"):
        config["WorkingDir"] = ""

    if config.get("User") == image_config.get("User"):
        config["User"] = ""

    if _network_mode_is_container(host_config):
        config["Hostname"] = ""

    entrypoint = config.get("Entrypoint")
    image_entrypoint = image_config.get("Entrypoint")
    if _slice_equal(entrypoint, image_entrypoint):
        config["Entrypoint"] = None
        if _slice_equal(config.get("Cmd"), image_config.get("Cmd")):
            config["Cmd"] = None

    health = config.get("Healthcheck")
    image_health = image_config.get("Healthcheck")
    if health and image_health:
        if _slice_equal(health.get("Test"), image_health.get("Test")):
            health["Test"] = None
        for field in ("Retries", "Interval", "Timeout", "StartPeriod"):
            if health.get(field) == image_health.get(field):
                health[field] = 0 if field == "Retries" else 0
        config["Healthcheck"] = health

    config["Env"] = _slice_subtract(config.get("Env"), image_config.get("Env"))
    config["Labels"] = _string_map_subtract(config.get("Labels"), image_config.get("Labels"))
    config["Volumes"] = _struct_map_subtract(config.get("Volumes"), image_config.get("Volumes"))

    exposed = dict(config.get("ExposedPorts") or {})
    image_exposed = image_config.get("ExposedPorts") or {}
    for port in list(exposed):
        if port in image_exposed:
            del exposed[port]
    for binding in (host_config.get("PortBindings") or {}):
        exposed[binding] = {}
    config["ExposedPorts"] = exposed

    config["Image"] = target_image
    config["Env"] = _patch_env(
        config.get("Env"),
        {
            "SELF_UPDATE_ENABLED": "true",
            "SELF_UPDATE_IMAGE": target_image,
        },
    )

    return config


def build_create_host_config(container_info: dict[str, Any]) -> dict[str, Any]:
    """Copy HostConfig, rewriting link aliases for recreate."""
    host_config = dict(container_info.get("HostConfig") or {})
    links = host_config.get("Links")
    if links:
        rewritten: list[str] = []
        for link in links:
            if ":" not in link:
                rewritten.append(link)
                continue
            name = link[: link.index(":")]
            alias = link[link.rfind("/") :]
            rewritten.append(f"{name}:{alias}")
        host_config["Links"] = rewritten
    return host_config


def build_networking_config(container_info: dict[str, Any]) -> dict[str, Any]:
    networks = (container_info.get("NetworkSettings") or {}).get("Networks") or {}
    endpoints: dict[str, Any] = {}
    for name, settings in networks.items():
        ep = dict(settings)
        aliases = [a for a in ep.get("Aliases", []) if a != container_info.get("Id", "")[:12]]
        if aliases:
            ep["Aliases"] = aliases
        else:
            ep.pop("Aliases", None)
        for drop in (
            "NetworkID",
            "EndpointID",
            "Gateway",
            "IPAddress",
            "IPPrefixLen",
            "IPv6Gateway",
            "GlobalIPv6Address",
            "GlobalIPv6PrefixLen",
            "MacAddress",
            "DriverOpts",
        ):
            ep.pop(drop, None)
        endpoints[name] = ep
    return {"EndpointsConfig": endpoints}


def _simple_network_config(networking_config: dict[str, Any]) -> dict[str, Any]:
    endpoints = networking_config.get("EndpointsConfig") or {}
    if not endpoints:
        return {"EndpointsConfig": {}}
    first_name = next(iter(endpoints))
    return {"EndpointsConfig": {first_name: endpoints[first_name]}}


def _is_host_network(host_config: dict[str, Any]) -> bool:
    return host_config.get("NetworkMode") == "host"


def recreate_from_inspect(
    client: DockerClient,
    *,
    source: str,
    name: str,
    target_image: str,
) -> str:
    container_info = client.container_inspect(source)
    if not container_info.get("Config") or not container_info.get("HostConfig"):
        raise DockerError("container inspect missing Config or HostConfig")

    old_image_ref = container_info.get("Image") or container_info["Config"].get("Image", "")
    old_image_info = client.image_inspect(old_image_ref)
    # Ensure target image exists locally (pull happens before recreate in updater).
    client.image_inspect(target_image)

    config = build_create_config(container_info, old_image_info, target_image)
    host_config = build_create_host_config(container_info)
    networking_config = build_networking_config(container_info)
    simple_network = _simple_network_config(networking_config)

    container_id = client.container_create(name, config, host_config, simple_network)

    if not _is_host_network(host_config):
        endpoints = networking_config.get("EndpointsConfig") or {}
        if len(endpoints) > 1:
            for net_name in endpoints:
                try:
                    client.network_disconnect(net_name, container_id, force=True)
                except DockerError:
                    pass
            for net_name, endpoint in endpoints.items():
                client.network_connect(net_name, container_id, endpoint)

    client.container_start(container_id)
    return container_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recreate a container from docker inspect data")
    parser.add_argument("--source", required=True, help="Source container name/id to inspect")
    parser.add_argument("--name", required=True, help="Name for the new container")
    parser.add_argument("--image", required=True, help="Target image reference")
    parser.add_argument("--socket", default=DEFAULT_SOCKET, help="Docker Unix socket path")
    args = parser.parse_args(argv)

    try:
        client = DockerClient(args.socket)
        container_id = recreate_from_inspect(
            client,
            source=args.source,
            name=args.name,
            target_image=args.image,
        )
    except (DockerError, OSError, KeyError, TypeError) as exc:
        print(f"recreate_from_inspect: {exc}", file=sys.stderr)
        return 1

    print(container_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
