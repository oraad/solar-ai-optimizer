# Vendored community-scripts helpers

Unmodified copies of [community-scripts/ProxmoxVE](https://github.com/community-scripts/ProxmoxVE) helper functions, fetched at runtime via `SOLAR_REPO_RAW` (see `proxmox/ct/solar-ai-optimizer.sh` curl wrapper).

**Pinned upstream commit:** `6c55f61efc960330dea01db3dad1fb9fa00acadf` (main, 2026-06-20)

**License:** MIT — see [upstream LICENSE](https://github.com/community-scripts/ProxmoxVE/blob/main/LICENSE)

## Files

| File | Upstream path |
|------|----------------|
| `misc/build.func` | Host LXC provisioning orchestration |
| `misc/api.func` | Telemetry API helpers |
| `misc/core.func` | Shared messaging, colors, utilities |
| `misc/error_handler.func` | Error handling |
| `misc/tools.func` | Addon/update tool helpers |
| `misc/install.func` | In-container install helpers (`motd_ssh`, `customize`, etc.) |
| `misc/alpine-install.func` | Alpine LXC install helpers (`motd_ssh`, `customize`, etc.) |

## Re-sync

```bash
SHA=6c55f61efc960330dea01db3dad1fb9fa00acadf  # or newer commit after testing
for f in build.func api.func core.func error_handler.func tools.func install.func alpine-install.func; do
  curl -fsSL "https://raw.githubusercontent.com/community-scripts/ProxmoxVE/${SHA}/misc/${f}" \
    -o "proxmox/vendor/community-scripts/misc/${f}"
done
```

Update the pinned SHA in this README after re-sync.
