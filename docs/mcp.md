# MCP (Model Context Protocol)

Solar AI Optimizer exposes an optional [MCP](https://modelcontextprotocol.io/) server so AI agents (Cursor, SDK automations) can read optimizer state, troubleshoot decisions, and apply the same safe overrides as the dashboard.

MCP is a **sidecar control plane** — it does not replace the real-time control loop. All writes go through the existing `Executor`, shadow mode, and `Override` safety model.

## When to use MCP vs the dashboard

| Use MCP when | Use the dashboard when |
|--------------|------------------------|
| Debugging engine logic with an AI agent | Day-to-day operator control |
| Correlating decisions with history from Cursor | Visual charts and settings UI |
| Scripting overrides with bearer auth | HA ingress viewer/admin roles |

## Security checklist

- **Bearer token = full admin.** `API_TOKEN` and `MCP_TOKEN` grant the same mutating access as a local admin.
- Prefer a dedicated `MCP_TOKEN` so you can revoke agent access without breaking CI scripts.
- HTTP MCP (`/mcp`) accepts **Bearer only** — no ingress cookies.
- Kill switch requires `confirm_kill_switch=true` (MCP) or `confirm=true` (REST).
- Treat tool outputs as untrusted (entity names can contain prompt-injection text).

## Configure from Settings (standalone / Proxmox / Docker)

1. Open **Settings → System → Agent access**.
2. Enable HTTP MCP, set or **Generate** a token, click **Save MCP** (writes `data/mcp.env` on the data volume).
3. Click **Restart service** in the sticky bar next to **Save changes** (Docker socket + self-update required).
4. Confirm health shows MCP mounted, then point Cursor at `http://<host>:8000/mcp` with the Bearer token.

On **Home Assistant apps**, use Apps options (`mcp_enabled` / `mcp_token`) and restart the app — Settings remains status-only for that path.

**Recreate container** (Software updates) is for host `solar.env` edits. A plain restart does **not** re-read host env files; `mcp.env` on the data volume is enough for Settings-driven MCP.

## Cursor setup (stdio)

1. Start the optimizer: `docker compose up -d solar`
2. Set a token: `export SOLAR_MCP_TOKEN=your-secret` (must match `API_TOKEN` or `MCP_TOKEN` on the container)
3. Copy [`.cursor/mcp.json.example`](../.cursor/mcp.json.example) to your user or project MCP config and adjust paths.
4. Restart Cursor → Settings → MCP → verify `solar-ai-optimizer` is connected.

The stdio server uses the `mcp` compose profile and talks to the running API at `http://host.docker.internal:8000`.

## Remote HTTP (Streamable)

```yaml
environment:
  MCP_ENABLED: "true"
  MCP_TOKEN: "change-me"
  # MCP_HTTP_PATH: /mcp   # optional, default /mcp
```

Or use Settings → Agent access (standalone). Mount is refused if no token is configured. Terminate TLS at your reverse proxy or HA ingress.

## Persistence notes

| Source | When |
|--------|------|
| `data/mcp.env` | Settings UI on standalone; loaded by `run.sh` when not an HA add-on |
| HA `options.json` | Add-on options → env at start |
| Host `solar.env` / Compose env | Bootstrap; recreate container after edits |

## Tool catalog

### Tier 1 — start here

| Tool | Purpose |
|------|---------|
| `solar_get_status` | Live telemetry, decision, shadow mode |
| `solar_explain_decision` | Full forensics trace (inputs → reasoning → execution) |
| `solar_simulate_decision` | Dry-run decision without writes |
| `solar_get_engine_config` | Redacted effective config |
| `solar_apply_override` | Apply `Override` fields |
| `solar_clear_override` | Clear overrides |

### Tier 2 — drill-down

`solar_get_forecast`, `solar_get_plan`, `solar_get_grid_stats`, history tools, `solar_get_shed_snapshots`.

### Tier 3 — mutating

`solar_trigger_cycle`, `solar_refresh_forecast`, `solar_update_config`.

## Troubleshooting playbook

1. **`solar_explain_decision`** — find the layer: forecast degraded? override active? MPC fallback? skipped write?
2. **`solar_get_engine_config`** — check reserve buffers, `priority_order`, subsystem enables.
3. **`solar_get_decision_history`** + **`solar_get_telemetry_window`** — input-driven vs logic bug.
4. **`solar_simulate_decision`** — test a config hypothesis without live writes.
5. If rationale keys point to a rule bug, fix code in `backend/app/engine/`.

Unauthenticated `POST /mcp` should return **401** Bearer required (not 405). If you see 405, the static UI may be swallowing `/mcp` — upgrade to a build that mounts MCP before the static catch-all.

## REST debug endpoints

Admin-only (same data as MCP forensics tools):

- `GET /api/debug/trace?sections=decision,execution,engine`
- `POST /api/debug/simulate` (rate-limited)

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_ENABLED` | `false` | Mount Streamable HTTP at `/mcp` |
| `MCP_HTTP_PATH` | `/mcp` | HTTP path |
| `MCP_TOKEN` | `""` | Agent bearer token; falls back to `API_TOKEN` |
| `SOLAR_API_URL` | `http://127.0.0.1:8000` | stdio client API base URL |

See also [Configuration](configuration.md).
