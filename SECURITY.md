# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.5.x   | Yes       |

## Reporting a Vulnerability

Please report security issues privately:

1. Open a [GitHub Security Advisory](https://github.com/oraad/solar-ai-optimizer/security/advisories/new), or
2. Email **omarraad@gmail.com** with a description and reproduction steps.

Do not open public issues for undisclosed vulnerabilities.

## Deployment Guidance

- When exposing the API outside Home Assistant ingress, set `LOCAL_ADMIN_PASSWORD_HASH` + `SESSION_SECRET` or `API_TOKEN`, and use HTTPS.
- Set `TRUST_INGRESS_HEADERS=true` only when the app is reachable exclusively via HA ingress (not directly on port 8000). This also sets `X-Frame-Options: SAMEORIGIN` for the sidebar iframe.
- Keep Home Assistant long-lived tokens scoped and rotated.
- Run in **shadow mode** until you trust automated inverter writes.
- The default Docker image includes optional ML/MPC extras; use `INSTALL_EXTRAS=0` for a leaner attack surface if those features are unused.

## Viewer role (ingress)

Non-admin HA users authenticated via ingress are **viewers**. They may read live status, forecasts, and history, and may POST limited overrides only:

- `shadow_mode`, `pause_engine`, `pause_shedding`, `pause_grid_charge`, `pause_optimization`, `force_grid_charge`, `force_shed_off`, `kill_switch` (with `confirm=true`)

Each `pause_*` field is bidirectional: `true` pauses, `false` resumes.

Viewers are denied config reads (`GET /api/config`), entity enumeration (`GET /api/entities`),
config writes, the Assistant, reserve pin, and other admin-only routes.
Enforcement is on the backend; the dashboard hides controls as defense-in-depth.

Do not expose port `8000` directly if viewers should not bypass HA ingress identity headers.
