# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.23] - 2026-06-26

### Added

- **Overview hero:** prominent battery SOC bar with reserve marker and blackout-risk pill at the top of Overview
- **Forecast insights:** excess solar estimate, peak load window, and reserve runway alongside the 48h chart; manual **Refresh** control for admins
- **History timeline:** telemetry chart renamed to **Timeline** with grid-outage shading; new **Activity** tab groups inverter writes, shed writes, and grid events with expandable rows
- Shared **blackout-risk** and **chart-lifecycle** helpers for consistent risk pills and chart theme/locale/date-format updates

### Changed

- **Decision panel:** collapsible details, shed action table, and quick links to shed history and load-shedding settings
- **Overrides panel:** grouped into Primary, Overrides, Advanced, and Danger zone sections
- **Load shedding** panel layout and tier display refreshed; priority labels localized
- **Status cards** streamlined under the new overview hero
- Forecast and history UI strings consolidated into locale catalogs (EN, AR, FR)

## [0.5.22] - 2026-06-26

### Added

- **Settings navigation:** category sidebar (Setup, Energy, Engine, Forecast, Safety, System) with search and a dismissible setup checklist
- **Azimuth compass:** visual azimuth input beside PV array direction fields in Site & PV settings
- Draft validation for latitude/longitude and grid charge min/max blocks save until issues are fixed

### Changed

- Settings panel reorganized around the new navigation structure; settings UI strings consolidated into locale catalogs (EN, AR, FR)

## [0.5.21] - 2026-06-26

### Changed

- **Site coordinates:** latitude and longitude moved from Forecast to **Site** settings; Open-Meteo timezone resolution and solar/weather APIs use `site.latitude` / `site.longitude`
- Config schema v5 migration moves legacy `forecast.latitude` / `forecast.longitude` to `site`

## [0.5.20] - 2026-06-26

### Fixed

- **Settings Site section:** `/api/config` now includes `site.timezone` so the Site accordion and timezone picker appear in the dashboard

## [0.5.19] - 2026-06-26

### Added

- **Site timezone:** new **Site** section in Settings with searchable IANA timezone picker or **Auto** (resolved from Open-Meteo at forecast location); daily solar/load totals, load-profile buckets, temperature bias hours, grid ramp hints, and dashboard date formatting use site-local time
- `timezone_config` and `timezone_resolved` on live status and `/health`
- Config schema v4 migration moves legacy `forecast.timezone` to `site.timezone`

### Changed

- **Decision panel** groups shed actions and results by tier with consolidated labels and entity tooltips
- **Load shedding** panel reuses shared tier-grouping display helpers

## [0.5.18] - 2026-06-25

### Added

- **Internationalization (i18n):** dashboard UI in English, العربية (Arabic, RTL), and Français; **Display preferences** in Settings for language and date format (locale default, DD/MM/YY, or ISO)
- Backend locale middleware (`X-Solar-Locale` / `Accept-Language`) for API errors, decision rationales, engine skip/reject reasons, system-update messages, and assistant heuristic fallbacks
- Shared locale catalogs (`frontend/src/locales/`, `backend/app/i18n/`) with parity tests and translation helper scripts
- Legacy English skip text in stored history rows normalized to catalog keys when re-fetched

### Changed

- Field labels and help text moved from inline TypeScript maps into locale JSON catalogs
- Changing language reconnects the live WebSocket and refetches history; chart axes and tables follow the selected date format

## [0.5.17] - 2026-06-25

### Added

- **Load shedding** tier blocks are collapsible; collapsed summary shows tier name, shed SOC, priority, and device count

### Changed

- **Load shedding** tiers and companion-entity sections default to collapsed
- **History** chart axis labels show date at day boundaries and `HH:mm` elsewhere; history tables and chart cursor use ISO dates
- **History** shed-write rows show entity friendly names (from the HA entity list) instead of raw IDs where available

### Fixed

- Chart x-axis no longer repeats the date on every tick when the visible range spans multiple days

## [0.5.16] - 2026-06-25

### Fixed

- **Entity inputs:** restore shadow-root datalists with theme styling; disable browser autocomplete; select `entity_id` on focus so typing replaces the value

### Changed

- Remove unused shared entity-datalist rendering helpers (each `solar-entity-input` owns its datalist)
- Dependency updates: Vite 8.1.0, pytest 9.1.1, Playwright 1.61.1, aiosqlite 0.22.1, PyYAML 6.0.3, python-dateutil 2.9.0.post0

## [0.5.15] - 2026-06-25

### Fixed

- **Load shedding** tier entity autocomplete: hoist HA entity list to app root so cold tab opens get populated datalists; stabilize shed domain bindings and add regression tests

## [0.5.14] - 2026-06-25

### Added

- **Load shedding** tier editor: dismiss (×) control per tier, icon buttons for add/remove entities, collapsible companion-entity sections
- Dashboard user guide screenshots for the dedicated **Load shedding** tab and mobile layouts (`mobile-*.png`)

### Changed

- Docs screenshot workflow captures Load shedding on its own tab (no longer nested under Settings)

## [0.5.13] - 2026-06-25

### Fixed

- **Software updates:** release and backup dates always use ISO format (`YYYY-MM-DD HH:mm`) instead of US-style locale dates on en-US browsers

## [0.5.12] - 2026-06-24

### Fixed

- **Info tips:** restore compact circled “i” on desktop/pointer devices; keep larger tap targets on touch screens
- **Load shedding** tier entity autocomplete: render datalists inside each entity input so suggestions work across shadow DOM boundaries (fixes empty datalist after v0.5.10)

### Changed

- **Entity inputs** own per-instance filtered datalists; Settings and Load shedding no longer render shared panel-level datalists

## [0.5.11] - 2026-06-24

### Added

- **Dependable Docker self-update:** versioned `docker-self-update.sh` helper with rename-first container swap, health-gated verification, and automatic rollback on failed recreate or health check
- Self-update **pull progress** (`pull_percent`) with layer-based percentage in the dashboard; new **verifying** stage with health-check attempt counter
- Helper logs written to `$DATA_PATH/.update-logs/latest.log` for failed install troubleshooting
- `self_update_health_timeout` setting (default 120s) for post-swap health wait

### Changed

- Dashboard **Install** spawns the **target image** as updater helper (not `docker:cli`) with `--entrypoint` override; restore uses the **current running image**
- Settings update progress: version header (`vX → vY`), pull progress bar, header chip shows current step, auto-open Software updates details, log path hint on failure
- Minimum self-update version raised to **0.5.10** (first release shipping the updater script)

### Fixed

- Dashboard self-update no longer stops and removes the container before the replacement is proven healthy; failed installs roll back to the previous container automatically

## [0.5.10] - 2026-06-24

### Fixed

- **Load shedding** tier entity inputs: restore Home Assistant entity autocomplete (datalist suggestions) after the tier editor moved to its own tab

### Changed

- Extract shared `entity-datalists` helpers used by Settings and Load shedding entity pickers

## [0.5.9] - 2026-06-24

### Added

- **Settings → Display preferences:** per-browser **Date format** (locale default, DD/MM/YY, or YYYY-MM-DD) for history tables, chart axes/cursor, and release dates
- Flexible datetime parsing for forecast ingestion (ISO and day-first formats)
- Self-update **container recreate** with automatic rollback to the previous image when the new image fails to start
- Proxmox **`update` recovery:** auto-recreates `solar-optimizer` when the container is missing but `solar.env` exists (e.g. after a failed dashboard install)

### Changed

- Enforce **Python 3.14+** in Docker, CI, pytest gate, and agent Cursor rules
- Upgrade frontend stack: Vite 7, Vitest 4, marked 18, jsdom 29, Playwright 1.x latest
- Upgrade backend deps to latest stable floors (FastAPI 0.138, pydantic 2.13+, uvicorn 0.49+, SQLAlchemy 2.0.51, etc.)
- Upgrade ML/MPC extras: numpy 2.5+, scikit-learn 1.9+, PuLP 3.3+
- Docs: mkdocs-material 9.7; SECURITY.md supported versions updated to 0.5.x
- Add `httpx2` dev dependency to silence Starlette TestClient deprecation warning
- Unify Docker and dev-tooling images on Debian 13 (Trixie): pin `python:3.14-slim-trixie` and `node:24-trixie`; replace Ubuntu Playwright (`jammy`) and Bookworm references in docs/scripts
- Software update UI waits for the update lock to clear, service health, and target version before reporting success; longer timeout on Proxmox hosts

### Fixed

- Dashboard update could report success while the service was still down or the container was not recreated

## [0.5.8] - 2026-06-24

### Added

- **Settings → Software updates:** release picker to install any recent stable version (upgrade or downgrade); pre-install data backup; backup restore for Docker self-update hosts
- `POST /api/system/update/restore` (admin) to recover from a failed install
- Markdown rendering for GitHub release notes in the dashboard
- Runtime config schema **v3** migration (`battery.max_grid_charge_a` → `grid_charge.max_grid_charge_a`)

### Changed

- **Max grid charge current (A)** moved from Battery settings to **Grid charge** (config key `grid_charge.max_grid_charge_a`)
- Settings **Save changes** bar moved to the bottom of the panel (after Advanced and model sections)
- Self-update pins `SELF_UPDATE_IMAGE` to the chosen release tag instead of always using `:latest`

### Fixed

- Restore after a failed upgrade now targets the pre-install release (`from_version`) instead of the broken target or an older `previous_image`
- Stale self-update locks older than 30 minutes are cleared automatically; failed-update details are exposed in `GET /api/system/update` for recovery UI

### Breaking

- `battery.max_grid_charge_a` removed — use `grid_charge.max_grid_charge_a` (runtime overrides auto-migrate on load)

## [0.5.7] - 2026-06-24

### Added

- Branded **boot splash** in the dashboard HTML that paints before JS loads when opening Solar AI via HA ingress (sun icon, spinner, “Verifying access…”); fades out after `/api/me` completes
- **Mobile ingress QA** checklist ([`docs/mobile-ingress-qa.md`](docs/mobile-ingress-qa.md)) for Home Assistant Companion validation
- Mobile screenshot captures (390×844) in the docs screenshot workflow
- Compact **status alerts menu** on narrow screens (≤600px) for secondary pills (RULES/MPC, UPDATE, forecast warnings, etc.)
- Horizontal scroll and snap for main nav tabs and History sub-tabs on mobile

### Changed

- Dashboard **mobile layout** for HA Companion ingress: safe-area insets (`viewport-fit=cover`), 44px tap targets, sticky topbar padding, bottom safe-area on main content and toasts
- Tab labels stay visible on narrow screens (short labels: “Shedding”, “Chat”)
- HA/LIVE pills use short labels on compact topbar widths
- History tables scroll horizontally without breaking page layout; chart axis padding tightens on narrow screens
- Info tips and touch controls improved for tap devices (`hover: none` button styles)
- Removed `background-attachment: fixed` on body to avoid double-scroll in ingress iframes
- Replaced `100vh` with `100%` min-height to reduce mobile browser chrome jump

### Fixed

- Logout shows the login page immediately instead of a stuck loading state

## [0.5.6] - 2026-06-24

### Added

- Dedicated dashboard **Load shedding** tab (admin): tier editor moved out of Settings with per-tier restore toggles and companion discovery
- Per-tier **`restore_enabled`** and **`restore_on_grid`** planner gates; optional **`state_entities`** map (omit key = autodiscover companions, `[]` = switch-only)
- Home Assistant **device-scoped companion autodiscovery** (climate, select, fan, etc.) via entity registry WebSocket lookup
- **Shed snapshot store** (`shed_snapshots.json`) capturing power and companion state before shed; prune on config reload
- Domain-specific **entity restore** (climate, select, fan, `input_select`, and related domains) with `was_on` gating — devices off before shed stay off
- **`GET /api/shed/device-companions`** and **`GET /api/shed/snapshots`** for discovery preview and snapshot inspection
- Decision panel and history show companion restore audit and was-off-before-shed details; `companion_audit_json` on shed execution records

### Changed

- Load shedding configuration UI, field labels, and help text aligned with new restore and companion semantics
- Shed executor captures snapshots before idempotency checks; shadow mode logs only (no snapshot persistence or HA writes)
- Companion restore runs when the power entity is already on at restore time

### Fixed

- Kill switch and restore paths honor pre-shed `was_on` snapshots so restore never powers on originally-off devices

## [0.5.5] - 2026-06-21

### Fixed

- **Dashboard self-update on Proxmox/Docker:** install `docker-cli` instead of `docker.io` in the image — Debian Trixie ships the daemon in `docker.io` but the client in `docker-cli`, so v0.5.2–0.5.4 images reported *Docker CLI is not available* even after a container recreate

## [0.5.4] - 2026-06-21

### Added

- Dashboard **toast notifications** for save/login/override/update feedback (loading, success, and error states)
- Software update API: `?refresh=true` to bypass the release cache; `release_checked_at` and `release_from_cache` in the response
- Periodic background update check for admins (every 15 minutes)

### Changed

- Settings, Overrides, Login, and Assistant use toasts instead of inline status text
- Self-update requires both Docker socket and Docker CLI in the container; clearer 503 message when CLI is missing

### Fixed

- **`GET /api/grid-stats` 500** when grid events exist in SQLite — normalize naive DB timestamps to UTC on read (`as_utc`)
- Grid-stats endpoint returns default stats on compute failure instead of HTTP 500
- Circular import in `app.engine` package (grid stats tests and imports via `app.grid`)

## [0.5.3] - 2026-06-21

### Added

- **Settings → Engine:** reorderable optimization priorities (resilience, savings, self-sufficiency) with per-priority effect tooltips and a live summary
- `engine.priority_order` config field and backend priority resolver that tunes reserve buffers, blackout risk scoring, MPC objective weights, and grid-charge ramp factor strength
- LLM assistant system prompt reflects the active priority order from config

### Changed

- Default priority order remains resilience → savings → self-sufficiency (behavior-neutral at default); reordering shifts engine tradeoffs
- README and docs describe configurable priorities and `engine.priority_order` in configuration reference

## [0.5.2] - 2026-06-21

### Added

- Dashboard **Settings → Software updates**: check GitHub releases, show release notes, and optional one-click update
- `GET/POST /api/system/update` (admin-only) with GitHub release check and opt-in Docker self-update
- `docker-compose.self-update.yml` overlay and Proxmox socket mount for dashboard-driven updates
- `scripts/changelog-excerpt.py`; release workflow populates GitHub release body from `CHANGELOG.md`
- Topbar **UPDATE** badge when a newer release is available (admin)

### Changed

- Docker image includes `docker.io` CLI to support self-update when the socket is mounted

## [0.5.1] - 2026-06-21

### Added

- Dashboard topbar shows the running app version (from `/api/me`)
- Root `VERSION` file as the single canonical release semver
- `scripts/sync-version.py` to sync or verify `config.yaml` and `frontend/package.json`
- CI drift check and release-tag validation against `VERSION`

## [0.5.0] - 2026-06-21

### Added

- Grid charge ramp engine: configurable factor chain (SOC gap, grid window, battery/load/solar signals, blackout risk) with per-cycle smoothing and Settings UI
- Grid stats card and ramp state on the dashboard; grid charge plan details in the decision panel
- Shell script `./scripts/reset-local-password.sh` to reset local admin credentials into `$DATA_DIR/local_auth.env` (Proxmox: `/opt/solar-ai-optimizer/reset-local-password.sh` or `solar_reset_local_password`)
- Runtime config schema v2 migration (`max_charge_a` → `max_grid_charge_a`, strip deprecated inverter keys)

### Changed

- **Breaking:** Removed inverter `work_mode` write capability and `battery.max_charge_a` setting. MPC charge/discharge bounds now derive from `max_grid_charge_a` and `nominal_voltage`.

### Fixed

- Grid charge disabled conservatively when telemetry is stale (matching load-shedding behavior)
- `enforce_hard_bounds` rejects out-of-range grid charge current writes
- Ramp state tracks idempotent skips and shadow-mode planned amps
- Remaining-solar factor uses site timezone for end-of-day window
- Grid stats cleared on compute failure (backend and frontend)

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

[0.5.10]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.10
[0.5.9]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.9
[0.5.8]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.8
[0.5.7]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.7
[0.5.6]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.6
[0.5.5]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.5
[0.5.4]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.4
[0.5.3]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.3
[0.5.2]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.2
[0.5.1]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.1
[0.5.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.5.0
[0.4.3]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.4.3
[0.4.2]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.4.2
[0.4.1]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.4.1
[0.4.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.4.0
[0.3.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.3.0
[0.2.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.2.0
[0.1.0]: https://github.com/oraad/solar-ai-optimizer/releases/tag/v0.1.0
