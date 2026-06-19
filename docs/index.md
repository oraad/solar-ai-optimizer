# Solar AI Optimizer

A self-hosted, vendor-agnostic brain for Home Assistant that forecasts solar and load,
then controls hybrid inverter charge/discharge settings to keep your home powered through
unpredictable grid outages.

## Quick links

- [Dashboard user guide](frontend-manual.md) — screenshot walkthrough of every tab
- [GitHub repository](https://github.com/oraad/solar-ai-optimizer) — source, issues, releases
- [Changelog](https://github.com/oraad/solar-ai-optimizer/blob/main/CHANGELOG.md)

## Get started

### Docker Compose

```bash
docker compose up -d --build
```

Open **http://localhost:8000**. The app starts in **shadow mode** (no inverter writes).

Pre-built image (after release):

```bash
docker pull ghcr.io/oraad/solar-ai-optimizer:latest
```

### Home Assistant add-on

1. Add repository: `https://github.com/oraad/solar-ai-optimizer`
2. Install **Solar AI Optimizer** from the add-on store
3. Open the ingress panel and configure entities in **Settings**

## Priorities

1. **Resilience** — never blackout critical loads
2. **Savings** — opportunistic grid use when available
3. **Self-sufficiency** — minimize wasted solar

The optimizer does **not** predict grid availability. It forecasts solar and load, defends
a conservative battery reserve, and reacts when the grid appears.

## Architecture

```
Home Assistant ──WebSocket──▶ Ingest ──▶ SQLite
        ▲                              │
        │ REST                         ▼
   Control Executor ◀── Engine ◀── Forecasters
        │
        ▼
   FastAPI + Lit dashboard
```

See the [README on GitHub](https://github.com/oraad/solar-ai-optimizer#readme) for API
details, configuration options, and safety notes.
