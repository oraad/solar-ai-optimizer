# Ingress and authorization

Solar AI Optimizer supports three ways to authenticate dashboard and API access:

1. **Home Assistant ingress** — HA login wraps the app; user identity comes from proxied headers.
2. **Local admin login** — username/password with a signed session cookie for standalone direct access.
3. **API bearer token** — `Authorization: Bearer <API_TOKEN>` for scripts and automation.

Ingress always takes priority: when trusted HA user headers are present, the local login page is bypassed.

## Deployment patterns

### A. Standalone with local login

Use when exposing the dashboard directly (e.g. `http://server:8000`).

```env
LOCAL_ADMIN_USERNAME=admin
LOCAL_ADMIN_PASSWORD_HASH=$2b$12$...   # bcrypt hash; prefer over plain password
SESSION_SECRET=long-random-string
TRUST_INGRESS_HEADERS=false
```

Generate a bcrypt hash:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"
```

The browser shows a login page until `POST /api/auth/login` succeeds. Sign out from **Settings → API security**. The login form supports browser password save and autofill (Chrome, Edge, Firefox).

### B. Standalone + hass_ingress (Docker)

HA users access the app through the HA sidebar; they do not use the local login page. Keep local login for direct `:8000` access if the port is published.

**Optimizer container:**

```env
LOCAL_ADMIN_USERNAME=admin
LOCAL_ADMIN_PASSWORD_HASH=...
SESSION_SECRET=...
TRUST_INGRESS_HEADERS=true
```

Do not publish port `8000` publicly when using ingress-only access.

When ingress is trusted — native add-on (`SUPERVISOR_TOKEN`) or `TRUST_INGRESS_HEADERS=true` — the backend sets `X-Frame-Options: SAMEORIGIN` so the HA sidebar iframe can embed the panel, and trusts proxied user identity headers. Standalone direct access (neither flag) keeps `DENY` and does not trust ingress headers.

**Home Assistant `configuration.yaml`:**

```yaml
ingress:
  solar_ai:
    title: Solar AI
    icon: mdi:solar-power-variant
    require_admin: false
    work_mode: ingress
    url: http://solar-ai-optimizer:8000
    headers:
      X-Remote-User-Id: $user_id
      X-Remote-User-Name: $username
      X-Remote-User-Display-Name: $user_name
```

Reload ingress in **Developer tools → YAML → INGRESS**.

For [hass_ingress](https://github.com/lovelylain/hass_ingress) (HACS), use `work_mode: ingress` and `ui_mode: normal`. Do not use `ui_mode: replace` — that mode is for embedding HA pages, not external apps. hass_ingress v1.3.0+ supports `$user_id`, `$username`, and `$user_name` in the `headers` block.

### C. Home Assistant add-on

When `SUPERVISOR_TOKEN` is set, ingress is trusted automatically (user headers and sidebar iframe framing). Local login is optional and off by default. Open the panel from the HA sidebar.

!!! info "Roles at a glance"
    **Admin** users see all five dashboard tabs (including Assistant and Settings).
    **Viewer** users see Overview, Forecast, and History only, with limited overrides on Overview.
    See the [Dashboard user guide → Dashboard roles](frontend-manual.md#dashboard-roles) for screenshots and the full feature matrix.

## Admin vs viewer (ingress users)

| Role | How determined | Dashboard |
|------|----------------|-----------|
| **Admin** | HA owner or `system-admin` group; or `ADMIN_USER_IDS` allowlist | Full dashboard (Overview, Forecast, History, Assistant, Settings) |
| **Viewer** | Other HA users via ingress | Overview, Forecast, and History only — limited operator controls on Overview |

Viewers can toggle **shadow/live**, **pause/resume** the engine, and engage the **kill switch** (with confirmation). They cannot pin reserve SOC, force grid charge, run a control cycle, refresh forecast, clear overrides, use the Assistant, or open Settings.

Mutating API routes enforce the same limits on the backend. Config and model APIs remain admin-only.

Optional break-glass allowlist:

```env
ADMIN_USER_IDS=abc123,def456
```

## API reference

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/me` | Session | Current user and role |
| `POST /api/auth/login` | Public | Local admin login; sets cookie |
| `POST /api/auth/logout` | Public | Clears session cookie |
| `GET /api/auth/status` | Public | `{ local_auth_enabled, login_required }` |
| `GET /api/health` | Public | Liveness probe |
| `GET /api/config` | Admin | Full dashboard config (viewers denied) |
| `GET /api/entities` | Admin | HA entity list for Settings autocomplete |
| `POST /api/override` | Session | Admin: any override field; viewer: `shadow_mode`, `pause_engine`, `kill_switch` only (`kill_switch` requires `confirm=true`) |

## Security checklist

- Use `LOCAL_ADMIN_PASSWORD_HASH`, not plain `LOCAL_ADMIN_PASSWORD`, in production.
- Set `SESSION_SECRET` to a long random value when local auth is enabled.
- Set `SESSION_COOKIE_SECURE=true` when served over HTTPS.
- Keep `API_TOKEN` for CI/scripts; it grants admin access without the login page.
- Block direct LAN access to port `8000` when all users should come through HA ingress.

## Troubleshooting

### Owner or admin sees VIEWER badge

1. Open DevTools → Network and check `GET .../api/me`. Expect `auth_mode: "ingress"` and `is_admin: true` for HA owners.
2. If `is_admin` is false, check optimizer logs for `config/auth/list failed` or `Failed to fetch HA config/auth/list`.
3. Ensure the HA long-lived token (env `HA_TOKEN` or **Settings → Home Assistant connection**) was created from an admin/owner account — the user list API requires admin credentials on the token.
4. Break-glass: set `ADMIN_USER_IDS=<your-user-id>` (copy `user_id` from `/api/me`) and restart the container.

### HA UI flashes inside the panel iframe on first load

Common with hass_ingress when the ingress URL lacks a trailing slash: relative asset paths resolve to `/api/ingress/assets/...` instead of `/api/ingress/<panel>/assets/...`, briefly loading HA's frontend.

1. Use `work_mode: ingress` and `ui_mode: normal` in your hass_ingress panel config.
2. In DevTools → Network, confirm JS bundles load from `/api/ingress/<panel>/assets/...`, not `/api/ingress/assets/...`.
3. Current builds inject a `<base href>` and trailing-slash redirect in the dashboard HTML to prevent this; upgrade if you still see the flash on an older image.
