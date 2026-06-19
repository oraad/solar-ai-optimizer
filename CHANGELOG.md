# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.1.0
