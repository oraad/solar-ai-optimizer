# Configuration

Solar AI Optimizer layers configuration from several sources. The **Settings** panel in
the dashboard is the primary interface for operators.

## Configuration sources

| Source | Purpose |
|--------|---------|
| **Settings UI** | Primary config: HA connection, entity map, battery, reserve, forecast, control |
| `config/config.yaml` (in image) | Base defaults; UI overrides stored in data volume |
| `config.runtime.yaml` (data volume) | Persisted UI edits (deep-merged over base) |
| `.env` / Compose `environment` | Secrets, feature flags, optional API token |
| HA add-on `options.json` | Mapped to env vars by `run.sh` when running as add-on |

Key sections (all editable in Settings):

- Home Assistant connection
- Inverter entity map (read sensors + write controls)
- Battery specs and reserve policy
- Forecast location, PV arrays, temperature model
- Control timing and engine mode (`rules` or `mpc`)
- Load-shedding tiers
- Fail-safe heartbeat

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
| `TRUST_INGRESS_HEADERS` | Trust HA ingress user headers (auto on add-on) |
| `API_TOKEN` | Bearer token for scripts; protects API when set |
| `CORS_ORIGINS` | Comma-separated CORS origins (default `*`) |
| `ML_LOAD_ENABLED` | Gradient-boosting load forecast (needs sklearn in image) |
| `LLM_ENABLED` / `OLLAMA_*` | Local LLM assistant (Phase 4) |
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
