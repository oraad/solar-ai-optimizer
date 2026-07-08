# Solar AI Optimizer for Home Assistant

[![CI](https://github.com/oraad/solar-ai-optimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/oraad/solar-ai-optimizer/actions/workflows/ci.yml)
[![Pages](https://github.com/oraad/solar-ai-optimizer/actions/workflows/pages.yml/badge.svg)](https://oraad.github.io/solar-ai-optimizer/)
[![CodeQL](https://github.com/oraad/solar-ai-optimizer/actions/workflows/codeql.yml/badge.svg)](https://github.com/oraad/solar-ai-optimizer/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A self-hosted, vendor-agnostic brain that watches your Deye (or any) hybrid inverter
through Home Assistant, forecasts solar and load, and reactively controls
charge/discharge/grid-charge settings to keep your home powered through
unpredictable outages while wasting as little solar as possible.

**Priorities, in order (default):** 1) resilience (never blackout critical loads),
2) savings, 3) self-sufficiency. Reorder them in **Settings → Engine**; default
order preserves the resilience-first stance.

Because the tariff is flat and the grid is unpredictable, the core intelligence
is **not** price optimization and **not** grid prediction. It is: forecast solar,
forecast load, and defend a conservative battery reserve so the home survives even
if the grid never returns. The grid is handled purely reactively - whenever it
appears, the optimizer grabs it; it is never assumed or predicted.

## Documentation

Full documentation: **https://oraad.github.io/solar-ai-optimizer/**

| Topic | Guide |
|-------|--------|
| Install | [Installation](https://oraad.github.io/solar-ai-optimizer/installation/) — Docker, Compose, HA app, Proxmox |
| Dashboard | [User guide](https://oraad.github.io/solar-ai-optimizer/frontend-manual/) — admin and viewer |
| Home Assistant | [HA setup](https://oraad.github.io/solar-ai-optimizer/home-assistant-setup/) · [Fail-safe](https://oraad.github.io/solar-ai-optimizer/home-assistant-failsafe/) |
| Access | [Roles and access](https://oraad.github.io/solar-ai-optimizer/ingress-auth/) |
| Config | [Configuration](https://oraad.github.io/solar-ai-optimizer/configuration/) |
| Proxmox | [Proxmox deployment](https://oraad.github.io/solar-ai-optimizer/proxmox/) |
| Security | [Security policy](https://oraad.github.io/solar-ai-optimizer/security/) |

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

## Quick start

No `.env` or `config.yaml` is required. Configure everything from the dashboard
Settings panel (persisted to the `solar-data` volume).

```bash
docker compose up -d --build
```

- Dashboard + API: http://localhost:8000
- API docs: http://localhost:8000/docs

Or pull a pre-built image — see [Installation](https://oraad.github.io/solar-ai-optimizer/installation/).

The service starts in **SHADOW MODE** (`SHADOW_MODE=true`): it logs every action
it *would* take but writes nothing to the inverter. Watch it for a day or two,
confirm the decisions look right, then switch to live control from the dashboard.

### Other deployment paths

- **Home Assistant app** — [HA setup guide](https://oraad.github.io/solar-ai-optimizer/home-assistant-setup/#supervisor-add-on)
- **Proxmox LXC** — [one-liner install](https://oraad.github.io/solar-ai-optimizer/proxmox/) (Debian or Alpine)

### Tests

```bash
docker compose run --rm test
docker compose run --rm frontend-test
```

## Local development

**Recommended:** use Docker for backend tests and parity with production (Python 3.14):

```bash
docker compose run --rm test
docker compose run --rm frontend-test
```

Backend (optional host venv — requires **Python 3.14+**; run `bash scripts/check-python.sh` first):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Git Bash / WSL / Linux
pip install -r ../backend/requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload
pytest
```

Frontend (Node **26+**):

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173 (proxies /api and /ws to :8000)
npm test
```

## The intelligence (phased)

- **Phase 0 - Foundations:** HA client, adapter, ingest, time-series storage, shadow mode.
- **Phase 1 - Forecasting:** solar via Open-Meteo (free) or Solcast, learned bias
  correction, temperature-aware load profile. Grid stats are display-only.
- **Phase 2 - Rule engine (default):** dynamic reserve floor, opportunistic grid
  top-up, discharge protection, blackout-risk score.
- **Phase 3 - MPC (optional):** LP battery dispatch (grid-absent assumption). Set
  `engine.mode: mpc` and install PuLP.
- **Phase 4 - Learning + LLM (optional):** ML load (`ML_LOAD_ENABLED`), Ollama assistant (`LLM_ENABLED`).
- **MCP (optional):** Agent control plane for Cursor and remote tools (`MCP_ENABLED`, `MCP_TOKEN`). See [docs/mcp.md](docs/mcp.md).

Configuration details: [Configuration guide](https://oraad.github.io/solar-ai-optimizer/configuration/).

## Safety (non-negotiable)

- **Shadow mode** is the default until you trust it.
- Every write is screened: bounds → watchdog → rate limit → read-back verification.
- **Kill switch** enables grid charge at max current, restores shed tiers, and pauses the engine. Use **Clear overrides** to resume.
- **Grid charge ramp:** Settings → Grid charge configures a cap chain that ramps max grid charge current up/down each cycle (emergencies still force max).
- **Fail-safe:** heartbeat to Home Assistant plus grid-charge-at-max on shutdown — see [Home Assistant fail-safe](https://oraad.github.io/solar-ai-optimizer/home-assistant-failsafe/).
- **Watchdog:** if Home Assistant is unreachable, writes stop; the inverter keeps
  its last safe configuration.

## API overview

`GET /api/health`, `GET /api/status`, `GET /api/forecast`, `GET /api/plan`,
`GET /api/grid-stats`, `GET /api/history/telemetry`, `GET /api/history/decisions`,
`GET /api/history/grid-events`, `GET /api/history/shed-executions`, `GET /api/config`,
`GET /api/entities`, `POST /api/cycle`, `POST /api/override`, `POST /api/model/retrain`,
`POST /api/assistant/ask`,
and `WS /ws` (pass `?token=<API_TOKEN>` when `API_TOKEN` or `MCP_TOKEN` is set; browsers cannot send `Authorization` on WebSocket handshakes).

Docker healthcheck hits `/api/health`. Prometheus scrape target: `GET /metrics` (pass `Authorization: Bearer <API_TOKEN>` when local auth or `API_TOKEN` is configured).

## Upgrading

```bash
docker rm -f solar-dashboard 2>/dev/null || true   # legacy container name
docker compose up -d --build
```

If upgrading from a release before the grid-charge ramp changes: remove `inverter.write.work_mode` and `inverter.work_modes` from your config (set work mode manually in Home Assistant), and use `grid_charge.max_grid_charge_a` instead of the removed `max_charge_a` / `battery.max_grid_charge_a`. Runtime overrides are migrated automatically on next load.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and pull requests are welcome on [GitHub](https://github.com/oraad/solar-ai-optimizer/issues).

## Data backup

The `solar-data` Docker volume holds `solar.db`, `config.runtime.yaml`, and
`model.json`. Back up this volume before upgrades. See [Configuration → Data backup](https://oraad.github.io/solar-ai-optimizer/configuration/#data-backup).
