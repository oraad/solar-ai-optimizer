# Home Assistant custom integration

Requires **Home Assistant Core 2026.3.0+**.

The [Solar AI Optimizer](https://github.com/oraad/solar-ai-optimizer) HACS integration replaces the legacy [YAML fail-safe package](home-assistant-failsafe.md) with:

- A **pairing code** so Home Assistant can talk to Solar without pasting `API_TOKEN`
- **Fail-safe watchdog** inside HA (polls Solar `/api/health`)
- An **Update** entity (install available on Docker/Proxmox when self-update is enabled; read-only on the Supervisor add-on)

IndieAuth (Solar → HA) for inverter writes remains available in Solar **Settings**; it is **not** required for the fail-safe or Update entity.

## Install (HACS)

1. HACS → Integrations → Custom repositories → add  
   `https://github.com/oraad/solar-ai-optimizer` as **Integration**.
2. Install **Solar AI Optimizer**, then restart Home Assistant.
3. Settings → Devices & services → Add integration → **Solar AI Optimizer**.

Manual install: copy `custom_components/solar_ai_optimizer/` into your HA `config/custom_components/` directory and restart.

## Pair Solar with Home Assistant

1. In the Solar dashboard (admin), open **Settings → Home Assistant connection** and generate a pairing code (or call `POST /api/pair/start` as admin).
2. Note the one-time code (`XXXX-XXXX`, valid ~10 minutes).
3. In the HA config flow, enter:
   - **URL** Solar is reachable on from HA Core (LAN `http://…:8000`, or Supervisor add-on hostname — **not** the ingress panel URL)
   - The pairing code
4. Optionally select grid-charge **switch** / **number** entities and stale/debounce thresholds for the fail-safe.

HA stores a minted `sol_c_…` client token in the config entry. Env `API_TOKEN` remains for scripts/MCP only.

### Add-on networking

When Solar runs as the Supervisor app, use the **direct** add-on HTTP URL on the Supervisor network (slug `solar_ai_optimizer`), not `/api/hassio_ingress/…`. Humans still use the ingress sidebar.

## Fail-safe

The integration owns a **healthy** binary sensor and watchdog:

- Unhealthy = Solar `heartbeat_last_pulse` older than the stale threshold for the debounce duration
- Action: turn on grid-charge enable + set max current (amps from Solar config or options)

**Before enabling the integration watchdog**, remove or disable `packages/solar-optimizer-failsafe.yaml` so grid charge is not applied twice.

## Software updates

The Update entity always appears. **Install** is offered only when Solar reports `can_apply` (typical Proxmox/Docker with Docker socket). On the Supervisor add-on, update via **Settings → Apps**.

## Revoke / reauth

- Solar Settings → revoke a paired client → HA looks like unauthorized until you reauth (new pairing code).
- Rotating env `API_TOKEN` does **not** revoke the HA client token.

## Related

- [Home Assistant setup](home-assistant-setup.md)
- [Fail-safe (legacy package)](home-assistant-failsafe.md)
- [Roles and access](ingress-auth.md)
- [Security](security.md)
