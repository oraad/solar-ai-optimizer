# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.3] - 2026-06-20

### Fixed

- Login page: username field now uses themed input styling (was missing `type="text"`)
- Login page: browser password managers can detect and save/fill credentials — light DOM form, uncontrolled inputs, and autofill styling

## [0.4.2] - 2026-06-20

### Fixed

- hass_ingress / add-on: HA owner and `system-admin` users no longer shown as viewers — admin lookup now uses the correct WebSocket command `config/auth/list` (was `auth/list`)
- hass_ingress: first-load flash of the Home Assistant UI inside the panel iframe — ingress bootstrap adds `<base href>` and enforces a trailing slash so relative assets resolve under `/api/ingress/<panel>/`
- WebSocket `/ws`: quieter handling of normal client disconnects (keepalive / close)
- Proxmox update helper selects the correct community-scripts CT script on Alpine vs Debian

### Changed

- `HAAdminResolver` stays in sync when HA credentials change via Settings (`set_ha` on reconnect)
- Dynamic API path prefix (`getBase()`) for ingress-safe fetch and WebSocket URLs
- Proxmox: Alpine LXC install path (`solar-ai-optimizer-alpine.sh`) and Docker install helper
- Ingress troubleshooting docs (VIEWER badge, iframe flash, hass_ingress config)

### Added

- Tests for HA admin resolver (`test_ha_users.py`) and WebSocket endpoint (`test_ws.py`)

## [0.4.1] - 2026-06-20

### Fixed

- Home Assistant sidebar iframe for hass_ingress and Proxmox deployments: set `X-Frame-Options: SAMEORIGIN` when ingress is trusted (`TRUST_INGRESS_HEADERS=true` or native add-on), instead of `DENY` blocking the panel

### Changed

- Documentation and tests for ingress iframe framing (`ingress_trusted` behavior)

## [0.4.0] - 2026-06-19

### Added

- Proxmox VE deployment: community-scripts-style helper scripts (`proxmox/ct/solar-ai-optimizer.sh`, install script, shared lib)
- Proxmox documentation: install, update, backup, troubleshooting, and future OCI notes ([proxmox/README.md](proxmox/README.md))
- CI check that production image exposes OCI metadata (labels, entrypoint, port)

### Changed

- Docker image: `ENTRYPOINT` instead of `CMD`, `STOPSIGNAL SIGTERM`, and OpenContainers / `io.oraad.solar.*` labels for future Proxmox OCI use

## [0.3.0] - 2026-06-19

### Added

- Home Assistant ingress authentication with admin vs viewer roles (`X-Remote-User-*` headers)
- Local admin login page with signed session cookie for standalone direct access
- Viewer dashboard: Overview, Forecast, and History tabs with limited operator controls (shadow/live, pause/resume, kill switch)
- `GET /api/me` session endpoint; `BatterySummary` on live status for viewer battery ETA without config access
- HA WebSocket admin lookup and optional `ADMIN_USER_IDS` break-glass allowlist
- Override audit logging (user, auth mode, fields)
- Documentation: [Ingress and authorization](docs/ingress-auth.md), viewer dashboard section in user guide

### Changed

- `POST /api/override`: viewers limited to `shadow_mode`, `pause_engine`, and `kill_switch`; admin-only for reserve pin, grid charge, clear, etc.
- `GET /api/config` and `GET /api/entities` require admin
- Assistant and Settings tabs hidden for viewers; auth loading gate prevents admin UI flash before session resolves
- Empty override requests return 400

## [0.2.0] - 2026-06-19

### Added

- Home Assistant heartbeat (`input_datetime` pulse each control cycle) for fail-safe staleness detection
- Fail-safe settings section: heartbeat entity, shutdown grid-charge-at-max
- Graceful shutdown hook: enable grid charge at max current before exit
- HA package example (`examples/home-assistant/packages/solar-optimizer-failsafe.yaml`) defining `input_datetime.solar_optimizer_heartbeat`
- Default heartbeat entity `input_datetime.solar_optimizer_heartbeat` in config and example YAML
- Documentation: [Home Assistant fail-safe](docs/home-assistant-failsafe.md)

### Changed

- **Breaking:** Kill switch now enables grid charge at max current instead of disabling grid charge and setting `self_use` work mode

## [0.1.0] - 2026-06-19

### Added

- Home Assistant integration via `HAEntityAdapter` (vendor-agnostic inverter entity map)
- Solar and load forecasting (Open-Meteo default, optional Solcast provider)
- Rule-based decision engine with optional MPC (PuLP) mode
- Shadow mode, kill switch, load-shedding tiers, and safety write pipeline
- Lit dashboard with Overview, Forecast, History, Assistant, and Settings tabs
- FastAPI REST + WebSocket API with optional bearer token auth
- Docker Compose quick start and Home Assistant add-on manifest
- CI/CD: tests, production image build, GHCR release, CodeQL, Dependabot
- Documentation site via GitHub Pages (MkDocs Material)

### Changed

- Reset runtime config schema to version 1 for the initial public release.
  Pre-release schema versions 2–4 are not migrated.

### Notes

- Dashboard user guide screenshots are included under `docs/images/frontend/`.

[0.4.3]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.4.3
[0.4.2]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.4.2
[0.4.1]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.4.1
[0.4.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.4.0
[0.3.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.3.0
[0.2.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.2.0
[0.1.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.1.0
