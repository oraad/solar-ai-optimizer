# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.12-beta.2] - 2026-07-14

### Fixed

- Session cookies default to non-Secure again so Proxmox/LAN HTTP login works (`SESSION_COOKIE_SECURE` was flipped true in beta.1)
- Proxmox install writes `SESSION_COOKIE_SECURE=false` and migrates existing `solar.env` on update
- `run.sh` loads `local_auth.env` / `mcp.env` without shell-expanding bcrypt `$2b$…` hashes; values are shell-quoted on write
- Proxmox mounts `solar.env` into the container and forces `-e SESSION_COOKIE_SECURE=false`; dashboard recreate re-reads that file (fixes env edits that were lost on Inspect-based recreate)

### Changed

- Docs: editing `solar.env` requires container **recreate** (`update` / stop+rm+`docker run --env-file`), not `docker restart`

## [0.6.12-beta.1] - 2026-07-13

### Added

- HA Apps Supervisor update UI shows release notes via `solar_ai_optimizer/CHANGELOG.md` (synced from root)
- Confirm dialogs for dangerous overrides; short-lived WS tickets; login rate limiting
- `/api/v1` alias + `/api/v1/ping`; history pagination (`items` / `next_cursor`) for decisions, executions, and sheds
- Decision deep-link pin (`#decision=…`) with fetch-by-id; history load-more
- Fail-closed security matrix documented in `docs/security.md`

### Changed

- HA Apps / brand landscape logo now uses the same sun/gear mark as the app icon
- Brand sources live in repo-root `brand/` (obsolete `custom_components/` removed from the solar server repo; HACS integration is [`oraad/solar-ai-integration`](https://github.com/oraad/solar-ai-integration))
- MCP bearer is MCP-plane only (REST/WS and ws-ticket reject); soft-deprecate `API_TOKEN`→MCP fallback and WS `?token=`
- Non-addon ingress requires `TRUSTED_PROXY_IPS` (fail closed when empty)
- Auth hot path runs paired-client matching off the event loop (`asyncio.to_thread`)

### Fixed

- HA Apps store refresh skipped Solar AI Optimizer because `prerelease_updates` used invalid nested `name`/`description` in the addon schema; option labels moved to `translations/`
- Logout cookie mirrors `Secure`; WS tickets bind session JTI and drop on logout
- Login page light DOM + injected styles so browser autofill works
- LiveSocket generation guards; overlapping confirm resolves prior as false
- V1 alias rejects `..` path escapes; SSRF blocks `fe80::/10` and fails closed on DNS when private disallowed
- OAuth finish re-validates HA URL from pending store
- Test image includes root `CHANGELOG.md` (`.dockerignore` exception) so `sync-version.py --check` passes in Docker

## [0.6.11] - 2026-07-13

### Added

- Adaptive reserve (smoothed house load / discharge proxy), grid present opportunity windows, and site import ceiling (`max_grid_import_w` / entity)
- Structured decide-time explanations with `cycle_id`, Overview **Intended vs Applied**, History join, and MCP/forensics `causality`
- HA `unit_of_measurement` normalization for power, temperature, SOC, and charge-current telemetry
- Load shedding **Auto / Force OFF**; pairing codes, IndieAuth (Solar→HA), and stable `install_id` for HA device identity
- Optional MCP control plane (Settings-driven enable/token, Docker/add-on `/mcp`, Agent access UI)
- Supervisor discovery + Zeroconf for HA auto-setup; HA connection diagnostics and **Retry HA connection**
- HA app option **Pre-release updates**; HA Apps store version tracks stable releases only

### Changed

- HACS integration lives in [`oraad/solar-ai-integration`](https://github.com/oraad/solar-ai-integration); app releases ship Docker only
- Solar→HA auth: Supervisor → IndieAuth → env `HA_TOKEN` only (no LLAT paste / YAML token persistence)
- Crash/hang protection is the HACS watchdog via in-process `heartbeat_last_pulse` on `/api/health` (no HA `input_datetime` helper)
- Operational API/WebSocket reads require auth; ingress viewers retain access; timestamps are site-local ISO
- Settings entity pickers prefer friendly names; Software updates progress and semver sorting improved

### Removed

- Full LLM Assistant stack (dashboard tab, `/api/assistant/ask`, MCP `solar_ask`, Ollama settings)
- `POST /api/ha/bootstrap`, Settings LLAT paste, and YAML `ha.token` persistence
- HA `input_datetime` heartbeat helper write and Settings heartbeat fields

### Fixed

- Load-shed snapshot/restore episode handling (`was_on`, companions, history skip noise)
- IndieAuth callback/retry rebuilds live HA client; clearer IP-ban / SSL / unreachable errors
- MPC reserve pin, update progress UX, and ingress History access after MCP hardening

## [0.6.11-beta.14] - 2026-07-13

### Removed

- HA `input_datetime` heartbeat helper write and Settings fields (`fail_safe.heartbeat_entity` / `heartbeat_enabled`); liveness for the HACS watchdog is in-process `heartbeat_last_pulse` on `/api/health`
- Setup checklist item for fail-safe heartbeat entity

### Changed

- Settings → Safety is shutdown grid-charge-at-max only; crash/hang protection is documented as the HACS integration
- Runtime config schema v8 strips obsolete `fail_safe.heartbeat_*` keys

## [0.6.11-beta.13] - 2026-07-12

### Fixed

- Software update progress no longer flashes all steps complete before the first poll; stale progress clears when the update is idle
- Self-update helper starts from the current image so the target image pull reports percent progress instead of a long silent “starting” phase

### Changed

- Entity picker prefers HA friendly names in the datalist (falls back to `entity_id` when names collide)
- Heartbeat entity picker uses a stable `input_datetime` domains list and shows a hint when no helpers are available

## [0.6.11-beta.12] - 2026-07-12

### Changed

- Max grid import entity picker uses HA `number` domain (not `sensor`); docs/locales updated
- Settings → Temperature: clearer **Site outdoor temperature** label and help (live actuals + Open-Meteo bias correction)
- Settings → Safety: HA connected/reload hint for heartbeat entity; clear stores empty string; entity datalist options expose friendly-name `label`

## [0.6.11-beta.11] - 2026-07-12

### Added

- Adaptive reserve: raise autonomy floor and solar-bridge using smoothed house load and discharge proxy (`max(load mean, discharge mean)`), with priority blend, hysteresis, and optional `adaptive_load_cap_w`
- Grid present opportunity windows: merge short absent gaps, track elapsed/remaining trusted window, and fade present-risk discount near window end
- Site import ceiling via `max_grid_import_w` and optional `max_grid_import_entity` (caps planning amps below inverter max)
- HA `unit_of_measurement` normalization for telemetry power (W/kW), temperature (°C/°F), SOC (%), and charge-current readback (A/mA)

### Changed

- Grid charge ramp uses **remaining** trusted present window; live `grid_present=false` still stops charge
- Settings entity help documents UoM-normalized canonical units
- GitHub release picker sorts by semver so `beta.10` ranks above `beta.9`

### Fixed

- MPC reserve pin uses `max(mpc, rules)`; no CRITICAL when MPC has no forecast; timestamp-aligned MPC load

## [0.6.11-beta.10] - 2026-07-12

### Added

- Structured decide-time `DecisionExplanation` with `cycle_id`, reserve source (`rules` | `mpc` | `operator`), risk breakdown, and grid-charge cap-chain binding factor
- Overview **Intended vs Applied** for reserve and grid charge; History joins by `cycle_id`
- Forensics / MCP `causality` section and `docs/decision-cycle.md` playbook for expected vs actual troubleshooting

### Changed

- `solar_explain_decision` and `GET /api/debug/trace` accept `causality` (legacy `reasoning` maps to decision+causality)
- Decision and History UI surface explanation steps and clearer reserve/grid-charge rationale

## [0.6.11-beta.9] - 2026-07-12

### Removed

- Full LLM Assistant stack: dashboard Assistant tab, `POST /api/assistant/ask`, `backend/app/llm`, MCP `solar_ask`, and `LLM_ENABLED` / `OLLAMA_*` settings

## [0.6.11-beta.8] - 2026-07-12

### Fixed

- Load-shed snapshots are captured **once per shed episode**: repeat shed cycles while a switch is already off no longer overwrite a good `was_on=True` snapshot (and companions), so grid/SOC restore can turn the load back on. Failed HA reads no longer invent `was_on=False`.
- Restore actions are only planned while a shed snapshot is pending; after a legitimate clear, `no_shed_snapshot` skips are no longer written to shed history
- Shed `already_set` skips are no longer written to shed history (steady-state while still enforcing OFF each cycle)
- Load-shed snapshots may be captured while the HA write watchdog is stale (so restore intent survives); shed writes stay blocked until HA is fresh. `ha_stale` shed skips are no longer written to shed history

## [0.6.11-beta.7] - 2026-07-12

### Fixed

- IndieAuth callback and **Retry connection** rebuild the live HA client so a new token is used without restarting Solar

## [0.6.11-beta.6] - 2026-07-12

### Removed

- `POST /api/ha/bootstrap` and Settings Advanced LLAT paste (use IndieAuth or env `HA_TOKEN`)
- YAML `ha.token` persistence and resolve path (cleared by config schema v7 migration)
- Add-on `run.sh` mapping for legacy `ha_token` / `ha_base_url` options (`api_token` mapping kept)

### Changed

- Solar→HA auth: Supervisor → IndieAuth → env `HA_TOKEN` only
- Settings keeps HA URL + verify SSL next to IndieAuth; no token field

### Fixed

- IndieAuth callback surfaces HA IP-ban (403), unreachable, and SSL errors instead of a generic `token_exchange_failed`
- IndieAuth token exchange honors the Settings **Verify SSL** flag for the Solar→HA token request

## [0.6.11-beta.5] - 2026-07-12

### Added

- Supervisor discovery publish for the HA Apps add-on so Home Assistant can auto-setup the integration
- Zeroconf / mDNS advertisement (`_solar-ai._tcp.local.`) for standalone LAN installs
- HA connection diagnostics (`ha_auth_mode`, WebSocket circuit/backoff) on health/status and admin retry
- Settings UI: auth-mode status, WebSocket error clarity, and **Retry HA connection**

### Changed

- Prefer Supervisor token (add-on) and IndieAuth / bootstrap (standalone) over pasting `HA_TOKEN`
- Add-on options schema drops `api_token`, `ha_base_url`, and `ha_token` (legacy env mapping kept one release)
- Config patches sanitize HA secrets by deploy mode (add-on never persists URL/token; live OAuth ignores token overwrite)
- Proxmox helper scripts resolve latest image tags from GitHub Releases (optional prereleases)

### Fixed

- HA WebSocket client resilience and reconnect/retry paths under auth and circuit failures

## [0.6.11-beta.4] - 2026-07-12

### Added

- Settings-driven MCP: Agent access can enable/token MCP via `data/mcp.env`, sticky-bar **Restart service**, and Software updates **Recreate container** (Docker/Proxmox with self-update)
- Admin APIs `GET/PUT /api/system/mcp`, `POST /api/system/restart`, `POST /api/system/recreate`

### Fixed

- MCP HTTP mount is registered before the static UI catch-all so `/mcp` is not swallowed (POST 405)
- `/api/health` `mcp_http_mounted` reflects the live mount (`app.state.mcp_server`), not settings inference alone
- Refuse MCP mount when enabled without a token (including HA add-on)

### Changed

- HACS integration moved to [`oraad/solar-ai-integration`](https://github.com/oraad/solar-ai-integration); this repo is app / HA Apps add-on only
- App releases ship Docker image only (no bundled `solar_ai_optimizer.zip`)

## [integration 0.1.0] - 2026-07-08

### Integration

- Initial independent integration semver line (decoupled from app `VERSION`)
- HACS IQS Platinum-shaped checklist, diagnostics, reconfigure, repairs, `validate-ha.yml`, release zip packaging
- Independent release tracks: app (`VERSION` / `v*` tags) vs HACS integration (`INTEGRATION_VERSION` / `integration-v*` tags)
- `sync-version.py` syncs integration manifest from `INTEGRATION_VERSION` (decoupled from app `VERSION`)
- HACS `zip_release` enabled; integration installs from `solar_ai_optimizer.zip` on GitHub Releases

## [0.6.11-beta.3] - 2026-07-08

### Added

- HACS integration IQS checklist (`quality_scale.yaml`), diagnostics, reconfigure flow, fail-safe incomplete repair, icons, and typed coordinator models
- `validate-ha.yml` (hassfest, HACS action, PHCC tests) and `solar_ai_optimizer.zip` packaging on GitHub Releases
- `scripts/package-ha-integration.sh` for flat-domain release zips (PR dry-run artifact)

### Changed

- HACS minimum Home Assistant version bumped to **2026.7.0** (`hacs.json`); CI uses PHCC / HA 2026.7.1
- Integration docs expanded (en/ar/fr): removal, options, entities, troubleshooting, limitations, use cases
- Release runbook gates on `validate-ha.yml` and requires `solar_ai_optimizer.zip` on the GitHub Release (`zip_release` flip is a follow-up after the first zip-bearing release)
- HA integration CI requires **≥95%** coverage and **mypy --strict** on the integration package (IQS Silver/Platinum checklist honesty)

## [0.6.11-beta.2] - 2026-07-08

### Added

- Settings **Agent access** section (`system_mcp`): read-only MCP status, security guidance, HTTP endpoint copy, and local agent (stdio) client config snippet
- `/api/health` MCP fields: `mcp_http_path`, `mcp_auth_configured`, `mcp_http_mounted`, `mcp_http_url`, and tool/auth failure counts (no secrets exposed)
- Mobile settings subsection strip and scroll-spy on narrow layouts; optional setup checklist item for agent access

### Changed

- Settings scroll offsets use measured `--app-chrome-height` from the app topbar (fixes section titles under sticky chrome)
- Settings scroll-spy uses dynamic `IntersectionObserver` margins and `scrollend`/stability release after nav jumps
- Settings search hides category/subsection pills; sticky save bar respects `--card-pad`

### Fixed

- Settings desktop sidebar no longer slides behind the app topbar on scroll

## [0.6.11-beta.1] - 2026-07-08

### Added

- HACS custom integration (`custom_components/solar_ai_optimizer/`): pairing codes, fail-safe watchdog, and Update entity (HA Core 2026.3.0+)
- One-time pairing (`XXXX-XXXX` → `sol_c_…` client tokens) and IndieAuth (Solar → HA) for non-add-on installs
- Stable `install_id` on `/api/health` for HA device identity
- Settings UI for pairing codes, client revoke, and IndieAuth connect (non-add-on)

### Changed

- Legacy YAML fail-safe package is deprecated in favor of the HACS integration

## [0.6.10-beta.3] - 2026-07-08

### Added

- Home Assistant app option **Pre-release updates** (`prerelease_updates`, default off): when enabled, the add-on checks GitHub for beta/RC builds and logs when a newer version is available
- Optional MCP control plane (FastMCP): DOCKER Compose profile, add-on options, and `/mcp` mount for agent tooling

### Changed

- HA app store manifest (`solar_ai_optimizer/config.yaml` `version`) tracks **stable releases only**; pre-releases no longer bump the Supervisor-offered version
- On HA Apps installs, in-app **Software updates** section and UPDATE badge are hidden; updates are managed in Home Assistant → Settings → Apps
- Operational API reads (`/api/status`, forecasts, plan, grid stats, all `/api/history/*`, `/metrics`, `WS /ws`) now require an authenticated session at the route level; viewers retain access via HA ingress identity
- Direct access to port `8000` without ingress headers is denied on add-on and `TRUST_INGRESS_HEADERS` deployments (no anonymous open session when ingress is trusted)
- WebSocket accepts `?token=` matching `API_TOKEN` or `MCP_TOKEN` for bearer-only deployments

### Fixed

- HA Supervisor was offered beta builds because pre-release `VERSION` was synced into the app manifest; store version stays on last stable (currently `0.6.9`) until GA
- Exact semver matching for “Running” / current release in Software updates (beta vs stable on the same base version no longer both show as current)
- HA ingress viewers can read full History (decisions, executions, shed activity) again after MCP hardening had incorrectly required admin on those routes

## [0.6.10-beta.2] - 2026-07-08

### Changed

- Heartbeat pulses Home Assistant with site-local wall clock (Settings → Site timezone); HA fail-safe package template uses `as_datetime | as_local` and a tunable stale threshold helper
- API and WebSocket timestamps are serialized in site-local ISO with offset; internal storage and staleness logic remain UTC

## [0.6.10-beta.1] - 2026-07-06

### Added

- Load shedding **Auto / Force OFF** operator control (mirrors grid charge **Auto / Force ON**): Force OFF pauses automatic shedding and turns off all configured tier devices each cycle until Auto or Running is selected
- Viewers may use shed Force OFF via `POST /api/override` (`force_shed_off`)

### Changed

- Load shedding and optimization **Running** toggles use green highlight when healthy (same as grid charge)

## [0.6.9] - 2026-07-06

### Changed

- Grid charge **Auto / Force ON** and **Running / Paused** are single flip toggles (same interaction as load shedding and optimization), with green highlight for healthy states
- Admin top bar: **Viewer** pill enters preview mode, **Admin** pill exits; role pill hidden for real viewer sessions and sized to match other status chips

## [0.6.8] - 2026-07-06

### Changed

- Grid charge **Auto / Force on** toggle co-located in the per-subsystem row (left segment); **Running / Paused** stays right-aligned with other subsystems
- **Force on** pauses automatic grid charge control and applies max safe current; **Auto**, **Running**, and **Resume all** return to optimizer control
- Viewers may use grid charge Auto / Force on via `POST /api/override` (`force_grid_charge`)
- Admin **Viewer preview** / **VIEWER** status pills match HA and subsystem chip styling in the top bar

## [0.6.7] - 2026-07-01

### Changed

- Viewer **Load shedding** tab shows Home Assistant friendly names for tier switches and companions instead of raw entity IDs; entity ID remains available on hover
- `GET /api/config/load-shedding` returns scoped `entities` and `connected` for viewer sessions (full `/api/entities` remains admin-only)
- Viewer History shed activity rows use the same scoped entity names

## [0.6.6] - 2026-07-01

### Added

- Read-only **Load shedding** tab for viewer (ingress) users with live status, tier ladder, and `GET /api/config/load-shedding`
- Admin **Viewer preview** toggle in the top bar to see the dashboard as a non-admin user
- Viewer override API: per-subsystem pause/resume (load shedding, grid charge, optimization) in addition to pause/resume all and kill switch

### Changed

- Overrides panel: subsystem pause controls in the primary section for admins and viewers; **Resume all** when any subsystem is paused
- Dashboard and ingress docs: viewer capabilities updated for Load shedding tab and subsystem pauses

## [0.6.6-beta.1] - 2026-06-30

### Added

- Read-only **Load shedding** tab for viewer (ingress) users with live status, tier ladder, and `GET /api/config/load-shedding`
- Admin **Viewer preview** toggle in the top bar to see the dashboard as a non-admin user
- Viewer override API: per-subsystem pause/resume (load shedding, grid charge, optimization) in addition to pause/resume all and kill switch

### Changed

- Overrides panel: subsystem pause controls in the primary section for admins and viewers; **Resume all** when any subsystem is paused
- Dashboard and ingress docs: viewer capabilities updated for Load shedding tab and subsystem pauses

## [0.6.5] - 2026-06-28

### Added

- Execution and shed history audit deduplication on the backend (skip DB writes when audit payload unchanged)
- Shared `history-audit` and `grid-charge-display` helpers with unit tests
- History timeline: entities column for shed execution rows

### Changed

- SoC bar: solid green band from 85% to 100% when max ceiling allows; status cards pass `max_soc_ceiling` to the fill gradient
- Live status: grid charge amps shown as a subline on the Grid tile; removed separate Grid charge and Battery temp tiles
- Overview hero: risk pill no longer duplicates the percent sign

### Fixed

- History timeline: collapse consecutive duplicate execution and shed rows in the client

### Added

- Shared `soc-bar` helper for battery SoC fill styling (min-floor gradient ramp) with unit tests
- Home Assistant app store assets (`icon.png`, `logo.png`) in `solar_ai_optimizer/`
- Decision audit deduplication tests (`test_decision_audit.py`)

### Changed

- Home Assistant app store: fix `repository.yaml` validation; app manifest in `solar_ai_optimizer/` pulls `ghcr.io/oraad/solar-ai-optimizer` (no on-host build)
- Installation and HA setup docs: Add-ons → Apps terminology; document Supervisor `/data` persistence
- `run.sh`: force `DATA_DIR=/data` via shared `scripts/lib/addon-data-dir.sh` (includes one-time migration from `/app/data`)
- Dockerfile: copy full `solar_ai_optimizer/` directory (manifest + store assets)
- Overview hero and status cards: SoC bar uses min-floor gradient ramp; hero mobile layout tweaks
- `sync-version.py --check`: verify HA app store `icon.png` / `logo.png` exist
- CI: verify HA app data-dir wiring (`scripts/test-run-sh-data-dir.sh`)
- Refreshed frontend doc screenshots under `docs/images/frontend/`

### Fixed

- Decision history: skip duplicate DB writes when audit payload unchanged
- Grid events history: API returns newest-first; remove redundant client sort

## [0.6.3] - 2026-06-27

### Changed

- Docker frontend build image: `node:24-trixie` → `node:26-trixie`
- Backend dependencies: bcrypt `>=5.0.0`, websockets `>=16.0`, httpx2 `>=2.5.0`, fastapi `0.138.1`
- CI: `actions/checkout` v7
- Frontend manual and README updated for Node 26; local dev `engines.node` set to `>=26`

### Fixed

- Vitest/jsdom `localStorage` on Node 25+ (in-memory shim in test setup)

## [0.6.2] - 2026-06-27

### Added

- **Self-update:** prune old Solar Docker images after successful dashboard upgrades and Proxmox `update` runs (default: keep 2 images); override with `IMAGE_RETENTION` or disable with `IMAGE_CLEANUP=0`

### Changed

- **Grid charge:** factor cap-chain order is fixed in the ramp engine; removed `grid_charge.factor_order` from config and Settings (schema v6 migration strips legacy overrides)
- **Settings:** sidebar navigation uses scroll spy and improved wide-layout behavior
- **Azimuth compass:** layout uses shared form styles for consistent width
- Frontend manual and installation docs updated for fixed cap-chain order and image retention env vars

## [0.6.1] - 2026-06-28

### Added

- **Software updates:** optional **Include beta releases** toggle (server-persisted); pre-releases appear in the release table with install support on self-update hosts; update notifications remain stable-only
- **Self-update:** recreate containers from `docker inspect` so dashboard **Install** preserves custom `docker run` ports, volumes, networks, and environment (Watchtower-style); falls back to the previous template when inspect recreate fails

### Changed

- Settings Software updates section documents beta opt-in and stable-only notification behavior
- Installation docs clarify that one-click install keeps existing container configuration

## [0.6.0] - 2026-06-27

### Added

- **Independent subsystems:** shedding, grid charge, and optimization can be enabled or disabled in Settings and paused independently from the Overrides **Advanced** section; **Pause all** / **Resume** still stops or restores every active subsystem
- **Deployment profiles** on live status (`full`, `shed_primary`, `shed_advisory`, `custom`) derived from subsystem configuration
- **Load shedding:** shed-only deployment preset (disables grid charge and optimization; optional advisory reserve)
- **Settings:** **Engine enabled** and **Grid charge enabled** toggles under Engine and Grid charge sections
- **Overview:** subsystem status pills (shedding, grid charge, optimization) alongside existing alerts
- **Assistant:** deterministic pause/resume parsing for individual subsystems
- **Static assets:** Brotli/gzip precompression at build time and `Accept-Encoding` negotiation in the backend
- **Documentation i18n:** French and Arabic MkDocs builds via `mkdocs-static-i18n`; locale parity check in CI
- Docs translated to `docs/*.fr.md` and `docs/*.ar.md`; refreshed frontend screenshots

### Changed

- Orchestrator, rule engine, and MPC honor `plan_optimization`, `plan_grid_charge`, and `plan_shedding` flags when subsystems are disabled or paused
- Legacy single `paused` runtime state migrates to per-subsystem pause flags on load
- **Overrides panel:** grouped Advanced controls for per-subsystem pause; force grid charge hidden when grid charge is disabled
- **Viewer mode:** per-subsystem Advanced pause controls remain admin-only; viewers keep Pause all / Resume and kill switch
- Frontend manual, ingress auth, installation, and related docs updated for subsystem controls and shed-only deployments

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
