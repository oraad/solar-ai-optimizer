# Home Assistant fail-safe (heartbeat watchdog)

When the solar-ai-optimizer stops or hangs, Home Assistant can detect a stale
heartbeat and enable grid charge at maximum current — the same resilience
action the optimizer applies on graceful shutdown or via the kill switch.

## Prerequisites

- solar-ai-optimizer connected to Home Assistant (add-on or Docker)
- Inverter **write** entities mapped in Settings → Inverter (grid charge enable + max grid charge current)
- Battery **Max grid charge current (A)** set in Settings → Battery

## Step 1 — Import the HA package

Copy [`examples/home-assistant/packages/solar-optimizer-failsafe.yaml`](https://github.com/oraad/solar-ai-optimizer/blob/main/examples/home-assistant/packages/solar-optimizer-failsafe.yaml) into your Home Assistant `packages/` directory (or merge into `configuration.yaml`).

The package defines:

| Entity | Purpose |
|--------|---------|
| `input_datetime.solar_optimizer_heartbeat` | Heartbeat timestamp (updated by the optimizer) |
| `input_number.solar_optimizer_max_grid_charge_a` | Max grid charge current for the fail-safe automation |
| `binary_sensor.solar_optimizer_healthy` | Template sensor (stale if heartbeat &gt; 120s) |

Edit placeholders before reloading:

- `switch.YOUR_GRID_CHARGE_ENTITY` — same as Settings → Inverter → Grid charge enable
- `number.YOUR_MAX_GRID_CHARGE_CURRENT` — same as Settings → Inverter → Max grid charge current
- `input_number.solar_optimizer_max_grid_charge_a` **initial** — match Battery → Max grid charge current (A)

Reload helpers, templates, and automations after editing.

## Step 2 — Configure the optimizer

In the dashboard **Settings** → **Fail-safe**:

| Field | Value |
|-------|--------|
| Heartbeat enabled | On |
| Heartbeat entity | `input_datetime.solar_optimizer_heartbeat` (default) |
| Shutdown fail-safe enabled | On (default) |

Save changes.

Verify in **Developer tools** → **States** that `input_datetime.solar_optimizer_heartbeat` updates every control loop interval (default ~30s).

If you already created the helper manually with a different entity ID, set **Heartbeat entity** to match.

## How it works

```text
Package creates     →  input_datetime.solar_optimizer_heartbeat
Optimizer (alive)   →  pulses that entity each control cycle
HA template sensor  →  binary_sensor.solar_optimizer_healthy (fresh if < 120s)
HA automation       →  if unhealthy for 2 min → grid ON + max current
Optimizer shutdown  →  grid ON + max current (before process exits)
Kill switch         →  grid ON + max current + pause + restore sheds
```

## Tuning

| Parameter | Suggested | Notes |
|-----------|-----------|--------|
| Template stale threshold | 90–120s | ~3–4× default 30s control loop |
| Automation `for:` | 2–3 min | Survives restarts without false triggers |
| `input_number.solar_optimizer_max_grid_charge_a` | Match optimizer battery config | HA has no direct read of optimizer settings |

## Limitations

- Heartbeat requires the optimizer process to run and reach Home Assistant.
- Graceful shutdown fail-safe does not run on `kill -9` or power loss — rely on the HA automation for hard crashes.
- The HA automation writes inverter entities directly; it does not call the optimizer API (which may be down).

## Health API

`GET /api/health` includes:

- `heartbeat_configured` — heartbeat entity set and enabled
- `heartbeat_last_pulse` — last successful pulse (ISO timestamp)

Metrics counters: `heartbeat_pulses_total`, `heartbeat_failures`.
