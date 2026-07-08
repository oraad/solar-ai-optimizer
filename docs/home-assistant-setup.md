# Home Assistant setup

Solar AI Optimizer is an **external application** that connects to Home Assistant over REST
and WebSocket. For fail-safe and software updates from HA itself, install the
**[HACS custom integration](https://oraad.github.io/solar-ai-integration/home-assistant-integration/)** (Home Assistant **2026.7+**).

Install from [`oraad/solar-ai-integration`](https://github.com/oraad/solar-ai-integration) — **not** this repository (this repo is the Solar app / HA Apps add-on only).

A legacy [YAML fail-safe package](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/) still exists for older setups;
prefer the integration and disable the package when both would run.

Choose your deployment path:

| Path | When to use |
|------|-------------|
| [Supervisor app](#supervisor-add-on) | HAOS or Supervised — recommended for most HA users |
| [Docker + hass_ingress](#docker-with-hass_ingress) | Standalone container on the same network as HA |
| [Standalone Docker](#standalone-docker) | Direct `:8000` access; optional local admin login |
| [HA custom integration](https://oraad.github.io/solar-ai-integration/home-assistant-integration/) | Fail-safe + Updates in HA (pairs with any of the above) |

After connecting, complete [entity mapping](#inverter-entity-discovery). For fail-safe,
use the [custom integration](https://oraad.github.io/solar-ai-integration/home-assistant-integration/) (or optionally the
[legacy package](#home-assistant-packages)).

---

## Long-lived access token {#long-lived-access-token}

Required for Docker and Proxmox when Solar must **write** inverter entities
(the HA app uses the Supervisor token when fields are left empty). Prefer
**IndieAuth** in Solar Settings when available.

The HACS integration talks **to** Solar with a **pairing code** (not this LLAT).
Scripts may still use env `API_TOKEN`.

1. In Home Assistant, open your **Profile** (bottom-left avatar).
2. Scroll to **Security** → **Long-Lived Access Tokens**.
3. Click **Create Token**, name it (e.g. `solar-ai-optimizer`), and copy the token immediately — it is shown only once.
4. In the optimizer dashboard → **Settings → Home Assistant connection**:
   - **URL:** `http://homeassistant.local:8123` or your HA IP (e.g. `http://192.168.1.10:8123`)
   - **Token:** paste the long-lived token
   - **Verify SSL:** enable if HA uses HTTPS with a valid certificate

For the **HA app**, leave URL/token empty to use `http://supervisor/core` and `SUPERVISOR_TOKEN`.

Rotate tokens periodically and revoke unused tokens from the same Security page.

---

## Supervisor app {#supervisor-add-on}

[![Open your Home Assistant instance and show the add repository dialog.](https://my.home-assistant.io/badges/redirect_repository.svg)](https://my.home-assistant.io/redirect/repository/?owner=oraad&repository=solar-ai-optimizer)

1. **Settings → Apps → App store → ⋮ → Custom repositories** → add:
   ```
   https://github.com/oraad/solar-ai-optimizer
   ```
2. Install **Solar AI Optimizer** and start it.
3. Open the **ingress panel** from the HA sidebar.
4. In **Settings**, configure latitude/longitude, PV arrays, and [inverter entities](#inverter-entity-discovery).

The app pulls `ghcr.io/oraad/solar-ai-optimizer` from GHCR (version tag from the app manifest); no build on the HA host.

Settings, telemetry, and learned models persist on the Supervisor **`/data`** volume. `run.sh` forces `DATA_DIR=/data` on app startup (overriding the image default `/app/data`) so UI config survives restarts and upgrades.

App options (Supervisor UI) map to environment variables via `run.sh`:

| App option | Environment variable |
|---------------|---------------------|
| `prerelease_updates` | `ADDON_PRERELEASE_UPDATES` |
| `shadow_mode` | `SHADOW_MODE` |
| `log_level` | `LOG_LEVEL` |
| `ha_base_url` / `ha_token` | `HA_BASE_URL` / `HA_TOKEN` |
| `solcast_api_key` | `SOLCAST_API_KEY` |
| `api_token` | `API_TOKEN` |

Ingress is trusted automatically when running as a Supervisor app (`SUPERVISOR_TOKEN`); set `TRUST_INGRESS_HEADERS=true` for external Docker/Proxmox deployments. This enables proxied user identity and `X-Frame-Options: SAMEORIGIN` for the sidebar panel.
See [Roles and access](ingress-auth.md) for admin vs viewer behavior.

### App updates

- The HA **app store manifest** promotes **stable** releases only. Pre-release builds publish to GHCR but do not change the store version until a stable GA release.
- Update via **Settings → Apps → Solar AI Optimizer → Update** when Supervisor shows an update.
- The in-app **Software updates** section is hidden on HA App installs (updates are managed by Supervisor).
- Optional **Pre-release updates** (app configuration): when enabled and the app is restarted, the optimizer checks for newer beta/RC builds and logs when one is available. Update manually via **Settings → Apps** when Supervisor offers a matching version. Users already on a beta build stay on it until a stable GA release or manual reinstall.

---

## Docker with hass_ingress {#docker-with-hass_ingress}

Use when the optimizer runs as a separate container but HA users should open it from the HA sidebar.

### 1. Optimizer container

Example `docker-compose.yml` service on the same Docker network as Home Assistant:

```yaml
services:
  solar-ai-optimizer:
    image: ghcr.io/oraad/solar-ai-optimizer:latest
    container_name: solar-ai-optimizer
    restart: unless-stopped
    environment:
      SHADOW_MODE: "true"
      TRUST_INGRESS_HEADERS: "true"
      DATA_DIR: /app/data
      DATABASE_URL: sqlite+aiosqlite:////app/data/solar.db
      # Optional direct admin access to :8000 (keep port unpublished if ingress-only):
      # LOCAL_ADMIN_USERNAME: admin
      # LOCAL_ADMIN_PASSWORD_HASH: ...
      # SESSION_SECRET: ...
    volumes:
      - solar-data:/app/data
    networks:
      - homeassistant
    # Do not publish 8000 publicly when using ingress-only access.

networks:
  homeassistant:
    external: true   # or shared with your HA stack

volumes:
  solar-data:
```

Configure HA URL/token in **Settings** after first start, or set `HA_BASE_URL` / `HA_TOKEN` in `environment`.

### 2. Home Assistant ingress block

Add to `configuration.yaml`:

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

Reload ingress: **Developer tools → YAML → INGRESS**.

Requires `TRUST_INGRESS_HEADERS=true` on the optimizer so HA can embed the panel in the sidebar (`X-Frame-Options: SAMEORIGIN`).

Full auth patterns: [Roles and access](ingress-auth.md).

---

## Standalone Docker {#standalone-docker}

```bash
docker compose up -d --build
```

Open **http://localhost:8000** directly. Optionally enable local admin login via
`LOCAL_ADMIN_PASSWORD_HASH` and `SESSION_SECRET` (see [Configuration](configuration.md)).

Set HA URL and token in **Settings** — no ingress wrapper required.

---

## Home Assistant packages {#home-assistant-packages}

Packages let you split YAML configuration into files under `config/packages/`.

### Enable packages in configuration.yaml {#enable-packages-in-configurationyaml}

If not already present:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Restart Home Assistant or reload core configuration after adding this block.

### Fail-safe heartbeat package

Copy the example package into your HA config:

```
config/packages/solar-optimizer-failsafe.yaml
```

Source file in the repository:
[`examples/home-assistant/packages/solar-optimizer-failsafe.yaml`](https://github.com/oraad/solar-ai-optimizer/blob/main/examples/home-assistant/packages/solar-optimizer-failsafe.yaml)

The package creates:

| Entity | Purpose |
|--------|---------|
| `input_datetime.solar_optimizer_heartbeat` | Heartbeat timestamp (site-local wall clock, pulsed by optimizer) |
| `input_number.solar_optimizer_heartbeat_stale_s` | Stale threshold (seconds) for healthy sensor |
| `input_number.solar_optimizer_max_grid_charge_a` | Max grid charge current for fail-safe automation |
| `binary_sensor.solar_optimizer_healthy` | Template sensor (`as_datetime \| as_local` age check) |

Before reloading, edit placeholders:

- `switch.YOUR_GRID_CHARGE_ENTITY` — same as Settings → Inverter → Grid charge enable
- `number.YOUR_MAX_GRID_CHARGE_CURRENT` — same as Settings → Inverter → Max grid charge current
- `input_number.solar_optimizer_max_grid_charge_a` **initial** — match Settings → Grid charge → Max grid charge current (A)

Reload **helpers**, **templates**, and **automations**. Then configure the optimizer side:
[Home Assistant fail-safe](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/).

---

## Inverter entity discovery {#inverter-entity-discovery}

The optimizer uses a **vendor-agnostic entity map** in Settings → Inverter entity map.
Logical capabilities (battery SOC, PV power, grid charge enable, etc.) map to your HA
entity IDs. When HA is connected, fields offer **autocomplete** from live entities.

Use **Developer tools → States** to find entity IDs. The tables below are **starting points**
— naming varies by integration version and device model.

### Read sensors

| Capability | Deye / Sunsynk (MSA) | Victron (Venus / HA) | Growatt |
|------------|----------------------|----------------------|---------|
| `pv_power` | `sensor.*_pv*_power` or `sensor.*_solar_power` | `sensor.*_pv_power` | `sensor.*_pv_power` |
| `load_power` | `sensor.*_load_power` | `sensor.*_ac_consumption` | `sensor.*_load_power` |
| `battery_soc` | `sensor.*_battery_soc` | `sensor.*_soc` | `sensor.*_battery_soc` |
| `battery_power` | `sensor.*_battery_power` | `sensor.*_battery_power` | `sensor.*_battery_power` |
| `grid_power` | `sensor.*_grid_power` | `sensor.*_grid_power` | `sensor.*_grid_power` |
| `grid_present` | `binary_sensor.*_grid_connected` | `binary_sensor.*_ac_input` | `binary_sensor.*_grid_status` |
| `battery_temp` | `sensor.*_battery_temperature` | `sensor.*_battery_temperature` | `sensor.*_battery_temp` |

### Write controls

| Capability | Deye / Sunsynk (MSA) | Victron | Growatt |
|------------|----------------------|---------|---------|
| `grid_charge_enable` | `switch.*_grid_charge` | integration-specific | `switch.*_grid_charge` |
| `max_grid_charge_current` | `number.*_grid_charge_current` | `number.*_max_charge_current` | `number.*_max_grid_charge` |

### Load shedding {#load-shedding}

Each tier accepts **multiple switch entities** (pool pump + heater, AC power switch, etc.).
Use `switch.*` or `input_boolean.*` entities for power control.

**Companion entities** (climate, select, fan, etc.) on the same Home Assistant device are
discovered automatically and snapshotted when shedding; they are restored when the tier
comes back. Devices that were **off before shedding** are never turned on by restore.

Per-tier options:

| Field | Purpose |
|-------|---------|
| `restore_enabled` | Restore on SOC when `soc >= restore_above_soc` |
| `restore_on_grid` | Restore when grid is present (if global flag is on) |
| `state_entities` | Optional override map of power entity → companion entity IDs |

Omit a key in `state_entities` to autodiscover companions; set `[]` for switch-only.

Configure in the dashboard **Load shedding** tab. Grid-charge **write** entities are not required for shedding-only deployments (use the shed-only preset on that tab). You still need inverter **read** sensors for battery SOC and grid presence.

See [Dashboard user guide → Load-shedding tiers](frontend-manual.md#load-shedding-tiers).

### Outdoor temperature (optional)

Settings → Forecast → Temperature → **Outdoor sensor entity** — any `sensor.*` reporting
°C for temperature-aware load forecasting.

---

## Verification checklist

1. Dashboard top bar shows **HA connected** (not offline).
2. Overview status cards show live SOC, PV, and load values.
3. Forecast tab shows a 48-hour chart (requires latitude/longitude in Settings).
4. Settings entity fields autocomplete when typing (requires valid token).
5. Fail-safe: `input_datetime.solar_optimizer_heartbeat` updates in HA Developer tools (if package imported).

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| **HA offline** | URL reachable from container; token valid; SSL setting matches HA |
| **Empty status cards** | Read entities mapped correctly; entities not `unavailable` in HA |
| **No forecast** | Latitude/longitude set; not `0,0` |
| **Writes fail** | Write entities mapped; shadow mode off; HA reachable |
| **Ingress 401/403** | `TRUST_INGRESS_HEADERS=true`; ingress URL matches container hostname |

## Related guides

- [Installation](installation.md) — Docker, HA app, Proxmox
- [Home Assistant fail-safe](https://oraad.github.io/solar-ai-integration/home-assistant-failsafe/) — heartbeat tuning
- [Roles and access](ingress-auth.md) — admin vs viewer
- [Configuration](configuration.md) — env vars and persistence
