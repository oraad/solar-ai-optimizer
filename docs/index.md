# Solar AI Optimizer

A self-hosted, vendor-agnostic brain for Home Assistant that forecasts solar and load,
then controls hybrid inverter charge/discharge settings to keep your home powered through
unpredictable grid outages.

## Quick links

| Topic | Guide |
|-------|--------|
| **Install** | [Installation and quick start](installation.md) — Docker, Compose, add-on, Proxmox |
| **Dashboard** | [Dashboard user guide](frontend-manual.md) — admin and viewer walkthrough |
| **Mobile (HA app)** | [Mobile ingress QA](mobile-ingress-qa.md) — Companion app checklist |
| **Home Assistant** | [HA setup](home-assistant-setup.md) · [Integration (HACS)](https://oraad.github.io/solar-ai-integration/home-assistant-integration/) · [Fail-safe package](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/) |
| **Access control** | [Roles and access](ingress-auth.md) — admin vs viewer |
| **Config** | [Configuration](configuration.md) · [`.env.example`](https://github.com/oraad/solar-ai-optimizer/blob/main/.env.example) |
| **Proxmox** | [Proxmox deployment](proxmox.md) |
| **Security** | [Security policy](security.md) |
| **Source** | [GitHub repository](https://github.com/oraad/solar-ai-optimizer) · [Changelog](https://github.com/oraad/solar-ai-optimizer/blob/main/CHANGELOG.md) |

## Get started

New to the project? Start with **[Installation and quick start](installation.md)**.

The fastest local path:

```bash
docker compose up -d --build
```

Open **http://localhost:8000**. The app starts in **shadow mode** (no inverter writes).

## Priorities

Default order (configurable in **Settings → Engine**):

1. **Resilience** — never blackout critical loads
2. **Savings** — opportunistic grid use when available (not tariff optimization)
3. **Self-sufficiency** — minimize wasted solar

Reorder the list to emphasize different tradeoffs. The default order preserves the
resilience-first stance described above.

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

See [Configuration](configuration.md) for settings sources, [Security](security.md) for
deployment hardening, and the [README on GitHub](https://github.com/oraad/solar-ai-optimizer#readme)
for API details and safety notes.

## Documentation languages

This site is published in **English** (default), **Français**, and **العربية**. Use the
language switcher in the site header to change locale. Arabic pages use right-to-left layout.

**Contributors:** English sources in `docs/*.md` are canonical. After editing English:

1. Re-run `python scripts/translate_docs.py` for affected pages (or `--force` for all).
2. Run `python scripts/check_docs_i18n.py` and `mkdocs build --strict` locally.
3. To add a language: extend `docs/i18n/locales.yaml`, add `nav_translations` and a language
   entry in `mkdocs.yml`, then run the translate script.

Machine-translated pages are a starting point — improve `.fr.md` / `.ar.md` files directly
when you can. Dashboard UI strings are separate; see
[Adding a dashboard language](frontend-manual.md#adding-a-dashboard-language-contributors)
in the user guide.
