# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[0.2.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.2.0
[0.1.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.1.0
