# Home Assistant setup

Solar AI Optimizer integrates with Home Assistant as an **external application** — it is
**not** a HACS custom integration or `custom_components/` platform. The optimizer connects
over REST and WebSocket, maps inverter entities from Settings, and optionally uses a small
HA **YAML package** for heartbeat fail-safe automation.

Choose your deployment path:

| Path | When to use |
|------|-------------|
| [Supervisor add-on](#supervisor-add-on) | HAOS or Supervised — recommended for most HA users |
| [Docker + hass_ingress](#docker-with-hass_ingress) | Standalone container on the same network as HA |
| [Standalone Docker](#standalone-docker) | Direct `:8000` access; optional local admin login |

After connecting, complete [entity mapping](#inverter-entity-discovery) and optionally
[import the fail-safe package](#home-assistant-packages).

---

## Long-lived access token

Required for Docker and Proxmox deployments (the add-on uses the Supervisor token automatically when fields are left empty).

1. In Home Assistant, open your **Profile** (bottom-left avatar).
2. Scroll to **Security** → **Long-Lived Access Tokens**.
3. Click **Create Token**, name it (e.g. `solar-ai-optimizer`), and copy the token immediately — it is shown only once.
4. In the optimizer dashboard → **Settings → Home Assistant connection**:
   - **URL:** `http://homeassistant.local:8123` or your HA IP (e.g. `http://192.168.1.10:8123`)
   - **Token:** paste the long-lived token
   - **Verify SSL:** enable if HA uses HTTPS with a valid certificate

For the **add-on**, leave URL/token empty to use `http://supervisor/core` and `SUPERVISOR_TOKEN`.

Rotate tokens periodically and revoke unused tokens from the same Security page.

---

## Supervisor add-on

1. **Supervisor → Add-on store → Repositories** → add:
   ```
   https://github.com/oraad/solar-ai-optimizer
   ```
2. Install **Solar AI Optimizer** and start it.
3. Open the **ingress panel** from the HA sidebar.
4. In **Settings**, configure latitude/longitude, PV arrays, and [inverter entities](#inverter-entity-discovery).

Add-on options (Supervisor UI) map to environment variables via `run.sh`:

| Add-on option | Environment variable |
|---------------|---------------------|
| `shadow_mode` | `SHADOW_MODE` |
| `log_level` | `LOG_LEVEL` |
| `ha_base_url` / `ha_token` | `HA_BASE_URL` / `HA_TOKEN` |
| `solcast_api_key` | `SOLCAST_API_KEY` |
| `api_token` | `API_TOKEN` |

Ingress is trusted automatically when running as an add-on (`SUPERVISOR_TOKEN`); set `TRUST_INGRESS_HEADERS=true` for external Docker/Proxmox deployments. This enables proxied user identity and `X-Frame-Options: SAMEORIGIN` for the sidebar panel.
See [Roles and access](ingress-auth.md) for admin vs viewer behavior.

---

## Docker with hass_ingress

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

## Standalone Docker

```bash
docker compose up -d --build
```

Open **http://localhost:8000** directly. Optionally enable local admin login via
`LOCAL_ADMIN_PASSWORD_HASH` and `SESSION_SECRET` (see [Configuration](configuration.md)).

Set HA URL and token in **Settings** — no ingress wrapper required.

---

## Home Assistant packages

Packages let you split YAML configuration into files under `config/packages/`.

### Enable packages in configuration.yaml

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
| `input_datetime.solar_optimizer_heartbeat` | Heartbeat timestamp (pulsed by optimizer) |
| `input_number.solar_optimizer_max_grid_charge_a` | Max grid charge current for fail-safe automation |
| `binary_sensor.solar_optimizer_healthy` | Template sensor (stale if heartbeat &gt; 120s) |

Before reloading, edit placeholders:

- `switch.YOUR_GRID_CHARGE_ENTITY` — same as Settings → Inverter → Grid charge enable
- `number.YOUR_MAX_GRID_CHARGE_CURRENT` — same as Settings → Inverter → Max grid charge current
- `input_number.solar_optimizer_max_grid_charge_a` **initial** — match Settings → Battery → Max grid charge current (A)

Reload **helpers**, **templates**, and **automations**. Then configure the optimizer side:
[Home Assistant fail-safe](home-assistant-failsafe.md).

---

## Inverter entity discovery

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
| `work_mode` | `select.*_energy_management_model` | `select.*_ess_mode` | varies |

### Work mode labels

Map logical modes in Settings → Inverter → Work mode labels to the exact option strings
your integration exposes (e.g. `Grid First`, `Battery First`, `Selling First`).

### Load shedding

Each tier accepts **multiple switch entities** (pool pump + heater, etc.). Use any
`switch.*` entities you want the optimizer to control. See
[Dashboard user guide → Load-shedding tiers](frontend-manual.md#load-shedding-tiers).

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

- [Installation](installation.md) — Docker, add-on, Proxmox
- [Home Assistant fail-safe](home-assistant-failsafe.md) — heartbeat tuning
- [Roles and access](ingress-auth.md) — admin vs viewer
- [Configuration](configuration.md) — env vars and persistence
