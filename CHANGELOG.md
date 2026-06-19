# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[0.3.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.3.0
[0.2.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.2.0
[0.1.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.1.0
