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
- Set `MCP_TOKEN` separately from `API_TOKEN` so you can revoke agent access without breaking CI scripts. Both tokens are accepted for REST and WebSocket auth; stdio `ApiBackend` calls the REST API with whichever token is configured.
- Setting `MCP_TOKEN` alone (without `API_TOKEN`) activates the auth gate and protects REST endpoints.
- On standalone deployments, **never** set `MCP_ENABLED=true` without `MCP_TOKEN` or `API_TOKEN`.
- On the HA add-on, `mcp_enabled` defaults to `false`. Enable only on trusted networks.
- HTTP MCP (`/mcp`) accepts **Bearer only** — no ingress cookies.
- Kill switch requires `confirm_kill_switch=true` (MCP) or `confirm=true` (REST).
- Treat tool outputs as untrusted (entity names can contain prompt-injection text).

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

Mount is refused on standalone if no token is configured. Terminate TLS at your reverse proxy or HA ingress.

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

`solar_trigger_cycle`, `solar_refresh_forecast`, `solar_update_config`, `solar_ask`.

## Troubleshooting playbook

1. **`solar_explain_decision`** — find the layer: forecast degraded? override active? MPC fallback? skipped write?
2. **`solar_get_engine_config`** — check reserve buffers, `priority_order`, subsystem enables.
3. **`solar_get_decision_history`** + **`solar_get_telemetry_window`** — input-driven vs logic bug.
4. **`solar_simulate_decision`** — test a config hypothesis without live writes.
5. If rationale keys point to a rule bug, fix code in `backend/app/engine/`.

### Worked examples

**Reserve too high:** In the trace, compare `decision.reserve.solar_bridge_soc` vs `autonomy_floor_soc`. Check `inputs.forecast.degraded_reasons` and `engine.priority_weights`.

**Writes skipped:** Check `execution.results[].skipped_reason` for `shadow_mode`, HA stale, or unmapped capability.

**MPC fallback:** Check `ops.metrics.mpc_fallbacks` and `engine.mpc_unavailable`.

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
