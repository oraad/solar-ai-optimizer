# Security

This page summarizes the project security policy. The canonical version is also at
[`SECURITY.md`](https://github.com/oraad/solar-ai-optimizer/blob/main/SECURITY.md) in the repository.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.5.x   | Yes       |

## Reporting a vulnerability

Please report security issues **privately**:

1. Open a [GitHub Security Advisory](https://github.com/oraad/solar-ai-optimizer/security/advisories/new), or
2. Email **omarraad@gmail.com** with a description and reproduction steps.

Do not open public issues for undisclosed vulnerabilities.

## Deployment guidance

- When exposing the API outside Home Assistant ingress, set `LOCAL_ADMIN_PASSWORD_HASH` + `SESSION_SECRET` or `API_TOKEN`, and use HTTPS.
- Set `TRUST_INGRESS_HEADERS=true` only when the app is reachable **exclusively** via HA ingress (not directly on port 8000). This also sets `X-Frame-Options: SAMEORIGIN` for the sidebar iframe.
- Keep Home Assistant long-lived tokens scoped and rotated. See [Connecting Solar to Home Assistant](home-assistant-setup.md#long-lived-access-token).
- Run in **shadow mode** until you trust automated inverter writes.
- The default Docker image includes optional ML/MPC extras; use `INSTALL_EXTRAS=0` for a leaner attack surface if those features are unused.
- Never enable `DEMO_MODE` on a system connected to a real inverter.

Full access-control details: [Roles and access](ingress-auth.md).

Operational API reads require an authenticated session (HA ingress identity, local login cookie, or bearer token). Only `GET /api/health` and `/api/auth/*` bootstrap routes are anonymous.

## Viewer role (ingress)

Non-admin Home Assistant users authenticated via ingress are **viewers**. They may read live
status, forecasts, and history, and may POST limited overrides only:

- `shadow_mode`, `pause_engine`, `pause_shedding`, `pause_grid_charge`, `pause_optimization`, `force_grid_charge`, `kill_switch` (with `confirm=true`)

Each `pause_*` field is bidirectional: `true` pauses, `false` resumes.

Viewers are denied config reads (`GET /api/config`), entity enumeration (`GET /api/entities`),
config writes, the Assistant, reserve pin, and other admin-only routes.
Enforcement is on the backend; the dashboard hides controls as defense-in-depth.

Do not expose port `8000` directly if viewers should not bypass HA ingress identity headers.

Dashboard walkthrough: [Viewer dashboard](frontend-manual.md#viewer-dashboard).
