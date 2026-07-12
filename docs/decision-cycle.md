# How a control cycle decides

Each loop is **sense → decide → execute → verify**.

1. **Inputs** — telemetry, forecast, grid stats (digest stored on the decision).
2. **Reserve** — rules compute solar-bridge vs autonomy floor; MPC or an operator pin may replace the target (`source`: `rules` | `mpc` | `operator`). Risk uses the **effective** target.
3. **Grid charge** — reactive/ramp cap chain sets enable + amps; the binding factor is the lowest ceiling.
4. **Shedding** — SOC/grid policy; restores only for entities with a shed snapshot.
5. **Execute** — HA writes when not shadow and not write-paused (`paused_grid_charge` / `paused_shedding`). Planning still runs when optimization is “paused.”
6. **Verify** — Overview shows intended vs applied for reserve and grid charge; join history by `cycle_id`.

If Overview disagrees with expected behavior, use **Live forensics** (admin) or MCP `solar_explain_decision` with the `causality` section — see [mcp.md](mcp.md).
