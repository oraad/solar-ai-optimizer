# Configuration

Solar AI Optimizer layers configuration from several sources. The **Settings** panel in
the dashboard is the primary interface for operators.

## Configuration sources

| Source | Purpose |
|--------|---------|
| **Settings UI** | Primary config: HA connection, site timezone, entity map, battery, reserve, forecast, control |
| `config/config.yaml` (in image) | Base defaults; UI overrides stored in data volume |
| `config.runtime.yaml` (data volume) | Persisted UI edits (deep-merged over base) |
| `.env` / Compose `environment` | Secrets, feature flags, optional API token |
| HA add-on `options.json` | Mapped to env vars by `run.sh` when running as add-on |

Key sections (all editable in Settings):

- Home Assistant connection
- **Site** — IANA timezone or **Auto** (from Open-Meteo at site latitude/longitude); site coordinates; drives forecast day boundaries, load/temperature learning buckets, dashboard display, and API/WebSocket timestamps (should match Home Assistant's configured timezone)
- Inverter entity map (read sensors + write controls)
- Battery specs and reserve policy
- Forecast provider, PV arrays, temperature model
- Control timing and engine mode (`rules` or `mpc`)
- **Subsystem enables** — `engine.enabled` (reserve/MPC/forecast), `grid_charge.enabled` (inverter grid-charge writes), `load_shedding.enabled` (tier switches); each can be toggled independently in Settings or the Load shedding tab
- Fail-safe — shutdown grid-charge-at-max (HA crash watchdog is the HACS integration)

**Load shedding** is configured in the dedicated **Load shedding** tab (not Settings).
See [Dashboard user guide → Load-shedding tiers](frontend-manual.md#load-shedding-tiers).

See [Home Assistant setup](home-assistant-setup.md) for connection and entity mapping,
and [Dashboard user guide → Settings](frontend-manual.md#settings) for a UI walkthrough.

## Optional environment variables

Documented in [`.env.example`](https://github.com/oraad/solar-ai-optimizer/blob/main/.env.example).
Common overrides:

| Variable | Purpose |
|----------|---------|
| `HA_BASE_URL` / `HA_TOKEN` | Home Assistant connection (or set in UI) |
| `SHADOW_MODE` | `true` = observe only (default) |
| `LOCAL_ADMIN_PASSWORD_HASH` / `SESSION_SECRET` | Local admin login for standalone access |
| `TRUST_INGRESS_HEADERS` | Trust HA ingress user headers and allow sidebar iframe (`SAMEORIGIN`; auto on add-on) |
| `API_TOKEN` | Bearer token for scripts; protects API when set |
| `CORS_ORIGINS` | Comma-separated CORS origins (default `*`) |
| `ML_LOAD_ENABLED` | Gradient-boosting load forecast (needs sklearn in image) |
| `MCP_ENABLED` / `MCP_TOKEN` / `MCP_HTTP_PATH` | MCP agent server — also configurable via Settings → Agent access (`data/mcp.env` on standalone; see [MCP](mcp.md)) |
| `SOLAR_API_URL` | stdio MCP client API base (host-side only) |
| `DEMO_MODE` | **Docs only** — synthetic telemetry; never in production |

When `API_TOKEN` is set, enter the same value in **Settings → API security**.

## Solcast (optional solar provider)

In Settings, set **forecast → provider** to `solcast`. Credentials are **not** stored in
the UI config — set environment variables (or HA add-on options):

| Variable | Purpose |
|----------|---------|
| `SOLCAST_API_KEY` | Bearer token from your Solcast account |
| `SOLCAST_RESOURCE_ID` | Rooftop site ID from the Solcast dashboard |

Both must be set when provider is `solcast`; otherwise the app falls back to Open-Meteo
and shows a misconfiguration warning.

## Logging

| Variable | Values | Default |
|----------|--------|---------|
| `LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR | INFO |
| `LOG_FORMAT` | `text`, `json` | text |

Set `LOG_FORMAT=json` for production log aggregators (one JSON object per line).

## Engine modes

| Mode | Description |
|------|-------------|
| `rules` | Default rule engine — dynamic reserve, reactive grid use |
| `mpc` | Optional LP battery dispatch (requires PuLP in image) |

Set **Engine → mode** in Settings. MPC falls back to rules if PuLP is unavailable.

### Grid present opportunity window

Under **Settings → Grid charge**, configure how long a present opportunity typically lasts (`max_continuous_present_minutes`, default 120) and a safety derating (`grid_window_safety_factor`, default 0.75). Short mid-window outages up to `max_outage_ignore_minutes` (default 30) are merged into one opportunity for averages and remaining-time charge urgency; live `grid_present=false` still stops charging. Optional `max_grid_import_w` / `max_grid_import_entity` (HA `number` entity, W or kW) caps planning amps below the inverter max when the site breaker is tighter.

### Reserve and adaptive load

`reserve.critical_load_w` and `min_autonomy_hours` are the configured survival baseline. With `adaptive_load_enabled` (default on), the autonomy floor and solar-bridge also respect a smoothed recent house load (mean of `load_power` over `adaptive_load_window_minutes`) and, when discharging, `max(0, -battery_power)` — the adaptive signal is **max(load mean, discharge mean)** so inverter conversion losses raise the floor without double-counting. Priority order scales how much of that smoothed load above critical is trusted: resilience-first uses more; savings- or self-sufficiency-first blends toward the configured critical load. Optional `adaptive_load_cap_w` caps the effective watts (default 3× critical). See [decision-cycle.md](decision-cycle.md).

### Optimization priority order

In **Settings → Engine**, reorder `priority_order` (default: resilience, savings,
self_sufficiency). The list must include each value exactly once. Example in
`config.runtime.yaml`:

```yaml
engine:
  mode: rules
  priority_order:
    - resilience
    - savings
    - self_sufficiency
```

Higher-ranked priorities influence reserve buffers, blackout-risk scoring, MPC
objective weights, and grid-charge ramp factor strength. **Savings** means
opportunistic grid use when present — not time-of-use or tariff optimization.

## Load shedding

Configure tiers in the dashboard **Load shedding** tab. Each tier can control
several power switches (`switch.*` or `input_boolean.*`) that shed and restore
together using SOC hysteresis. Lower **priority** sheds first.

Companion entities on the same Home Assistant device (climate, select, fan, etc.)
are discovered automatically and snapshotted when shedding; they are restored when
the tier comes back. Devices that were **off before shedding** are never turned
on by restore.

Snapshots are captured **once per shed episode** (first time a power entity is
shed) and held until restore, clear, or config prune. Later shed cycles while the
switch stays off do not re-capture or overwrite that snapshot. A snapshot may be
captured even when the HA write watchdog is stale; the OFF write still waits until
HA is fresh.

| Field | Purpose |
|-------|---------|
| `restore_enabled` | Restore on SOC when `soc >= restore_above_soc` |
| `restore_on_grid` | Restore when grid is present (if global flag is on) |
| `state_entities` | Optional map of power entity → companion entity IDs |

Omit a key in `state_entities` to autodiscover companions; set `[]` for
switch-only shedding. Snapshots persist under the data volume and are pruned
when tier configuration changes.

API (admin): `GET /api/shed/device-companions?entity_id=…` previews discovery;
`GET /api/shed/snapshots` lists stored pre-shed state.

See [Home Assistant setup → Load shedding](home-assistant-setup.md#load-shedding)
for entity examples.

## Docker build extras

The default image installs Phase 3/4 extras (PuLP, scikit-learn, numpy) via `INSTALL_EXTRAS=1`.
For a lean image:

```bash
docker compose build --build-arg INSTALL_EXTRAS=0
```

## Data backup

The `solar-data` Docker volume (or add-on `/data`) holds:

- `solar.db` — telemetry and audit history
- `config.runtime.yaml` — UI config overrides
- `model.json` — learned forecast bias / load profile

Back up this volume before upgrades. See [Proxmox deployment → Backup](proxmox.md#backup)
for an example tar command.

## Upgrading

```bash
docker compose up -d --build
```

Mutating API endpoints require `Authorization: Bearer <token>` when `API_TOKEN` is set.
