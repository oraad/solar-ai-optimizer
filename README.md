# Solar AI Optimizer for Home Assistant

[![CI](https://github.com/oraad/solar-ai-optimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/oraad/solar-ai-optimizer/actions/workflows/ci.yml)
[![Pages](https://github.com/oraad/solar-ai-optimizer/actions/workflows/pages.yml/badge.svg)](https://oraad.github.io/solar-ai-optimizer/)
[![CodeQL](https://github.com/oraad/solar-ai-optimizer/actions/workflows/codeql.yml/badge.svg)](https://github.com/oraad/solar-ai-optimizer/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A self-hosted, vendor-agnostic brain that watches your Deye (or any) hybrid inverter
through Home Assistant, forecasts solar and load, and reactively controls
charge/discharge/grid-charge settings to keep your home powered through
unpredictable outages while wasting as little solar as possible.

**Priorities, in order:** 1) resilience (never blackout critical loads),
2) savings, 3) self-sufficiency.

Because the tariff is flat and the grid is unpredictable, the core intelligence
is **not** price optimization and **not** grid prediction. It is: forecast solar,
forecast load, and defend a conservative battery reserve so the home survives even
if the grid never returns. The grid is handled purely reactively - whenever it
appears, the optimizer grabs it; it is never assumed or predicted.

## Architecture

```
Home Assistant ──WebSocket(state)──▶ Ingest ──▶ SQLite (time-series + grid events)
        ▲                                            │
        │ REST (service calls, verified)             ▼
   Control Executor ◀── Decision Engine ◀── Forecasters (Open-Meteo / Solcast + load)
        │                     ▲
        │                     └── UI-editable config (persisted to data volume)
        ▼
   FastAPI (REST + WS) ──▶ Lit dashboard
```

The inverter is abstracted behind an `InverterAdapter`. The included
`HAEntityAdapter` maps logical capabilities to HA entity IDs from the Settings panel,
so swapping entity IDs makes it work with Sunsynk, Victron, Growatt, etc.

## Quick start (Docker)

No `.env` or `config.yaml` is required. Configure everything from the dashboard
Settings panel (persisted to the `solar-data` volume).

```bash
docker compose up -d --build
```

Or pull a pre-built image:

```bash
docker pull ghcr.io/oraad/solar-ai-optimizer:latest
```

Only the `solar` app service starts by default. To run tests:

```bash
docker compose run --rm test
docker compose run --rm frontend-test
# or: docker compose --profile test up --abort-on-container-exit
```

- Dashboard + API: http://localhost:8000
- API docs: http://localhost:8000/docs

## Dashboard user guide

See the [documentation site](https://oraad.github.io/solar-ai-optimizer/) or
[docs/frontend-manual.md](docs/frontend-manual.md) for a screenshot walkthrough of every tab
(Overview, Forecast, History, Assistant, Settings).

The service starts in **SHADOW MODE** (`SHADOW_MODE=true`): it logs every action
it *would* take but writes nothing to the inverter. Watch it for a day or two,
confirm the decisions look right, then switch to live control from the dashboard.

### Optional environment variables

Set via `docker-compose.yml` `environment:` or an optional `.env` file (see
`.env.example`). Common overrides:

| Variable | Purpose |
|----------|---------|
| `HA_BASE_URL` / `HA_TOKEN` | Home Assistant connection (or set in UI) |
| `SHADOW_MODE` | `true` = observe only (default) |
| `LOCAL_ADMIN_PASSWORD_HASH` / `SESSION_SECRET` | Local admin login for standalone direct access |
| `TRUST_INGRESS_HEADERS` | Trust HA ingress user headers (auto on add-on) |
| `API_TOKEN` | Bearer token for scripts; also protects API when set |
| `CORS_ORIGINS` | Comma-separated CORS origins (default `*`) |
| `ML_LOAD_ENABLED` | Enable gradient-boosting load forecast (needs sklearn in image) |

When `API_TOKEN` is set, enter the same value in **Settings → API security**. For
local login and HA ingress (admin vs viewer roles), see
[docs/ingress-auth.md](docs/ingress-auth.md).

## Home Assistant add-on

1. Add the repository URL `https://github.com/oraad/solar-ai-optimizer` in Supervisor → Add-on store → Repositories.
2. Install the add-on (root `config.yaml` includes `build:` for local builds).
3. Open the ingress panel; configure HA URL/token, **latitude/longitude**, PV arrays, and inverter entities in Settings.

The add-on uses `/data` for the database, runtime config overrides, and learned model.
`run.sh` maps `options.json` fields to environment variables automatically.

## Local development

Backend:

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173 (proxies /api and /ws to :8000)
npm test      # vitest unit tests (api.ts, basePrefix, auth)
```

## Configuration

| Source | Purpose |
|--------|---------|
| **Settings UI** | Primary config: HA connection, entity map, battery, reserve, forecast, control |
| `config/config.yaml` (in image) | Base defaults; UI overrides stored in data volume |
| `.env` / compose `environment` | Secrets, feature flags, optional API token |

Key sections (all editable in Settings): inverter entity map, battery specs,
reserve policy, forecast location/arrays/temperature model, control timing,
engine mode (`rules` or `mpc`), load-shedding tiers.

### Solcast (optional solar provider)

In Settings, set **forecast → provider** to `solcast`. Credentials are **not**
stored in the UI config — set environment variables (or HA add-on options):

| Variable | Purpose |
|----------|---------|
| `SOLCAST_API_KEY` | Bearer token from your Solcast account |
| `SOLCAST_RESOURCE_ID` | Rooftop site ID from the Solcast dashboard |

Both must be set when provider is `solcast`; otherwise the app falls back to
Open-Meteo and shows a misconfiguration warning.

### Logging

| Variable | Values | Default |
|----------|--------|---------|
| `LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR | INFO |
| `LOG_FORMAT` | `text`, `json` | text |

Set `LOG_FORMAT=json` for production log aggregators (one JSON object per line).

## The intelligence (phased)

- **Phase 0 - Foundations:** HA client, adapter, ingest, time-series storage, shadow mode.
- **Phase 1 - Forecasting:** solar via Open-Meteo (free) or Solcast, learned bias
  correction, temperature-aware load profile. Grid stats are display-only.
- **Phase 2 - Rule engine (default):** dynamic reserve floor, opportunistic grid
  top-up, discharge protection, blackout-risk score.
- **Phase 3 - MPC (optional):** LP battery dispatch (grid-absent assumption). Set
  `engine.mode: mpc` and install PuLP.
- **Phase 4 - Learning + LLM (optional):** ML load (`ML_LOAD_ENABLED`), Ollama assistant (`LLM_ENABLED`).

## Safety (non-negotiable)

- **Shadow mode** is the default until you trust it.
- Every write is screened: bounds → watchdog → rate limit → read-back verification.
- **Kill switch** enables grid charge at max current, restores shed tiers, and pauses the engine. Use **Clear overrides** to resume.
- **Fail-safe:** heartbeat to Home Assistant plus grid-charge-at-max on shutdown; configure HA automation for when the optimizer is dead — see [Home Assistant fail-safe](docs/home-assistant-failsafe.md).
- **Watchdog:** if Home Assistant is unreachable, writes stop; the inverter keeps
  its last safe configuration.

## API overview

`GET /api/health`, `GET /api/status`, `GET /api/forecast`, `GET /api/plan`,
`GET /api/grid-stats`, `GET /api/history/telemetry`, `GET /api/history/decisions`,
`GET /api/history/grid-events`, `GET /api/history/shed-executions`, `GET /api/config`,
`GET /api/entities`, `POST /api/cycle`, `POST /api/override`, `POST /api/model/retrain`,
`POST /api/assistant/ask`,
and `WS /ws` (pass `?token=` when `API_TOKEN` is set).

Docker healthcheck hits `/api/health` (includes `metrics` counters). Prometheus scrape target: `GET /metrics`.

### Docker build extras

The default image installs Phase 3/4 extras (PuLP, scikit-learn, numpy) via `INSTALL_EXTRAS=1`.
For a lean image: `docker compose build --build-arg INSTALL_EXTRAS=0`.

## Upgrading

```bash
docker rm -f solar-dashboard 2>/dev/null || true   # legacy container name
docker compose up -d --build
```

Mutating endpoints require `Authorization: Bearer <token>` when `API_TOKEN` is set.

## Documentation

Full documentation is hosted on GitHub Pages: **https://oraad.github.io/solar-ai-optimizer/**

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and pull requests are welcome on [GitHub](https://github.com/oraad/solar-ai-optimizer/issues).

## Data backup

The `solar-data` Docker volume holds `solar.db`, `config.runtime.yaml`, and
`model.json`. Back up this volume before upgrades.
