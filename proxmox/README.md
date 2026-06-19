# Proxmox deployment

Deploy **Solar AI Optimizer** on Proxmox VE using a [community-scripts](https://github.com/community-scripts/ProxmoxVE)-style helper that creates a Debian LXC, installs Docker, and runs the published GHCR image.

## Quick install

Run on your **Proxmox host** (as root):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

The wizard provisions:

- Debian 13 LXC with **nesting** and **keyctl** (required for Docker-in-LXC)
- Docker Engine + Compose plugin
- Container `solar-optimizer` from `ghcr.io/oraad/solar-ai-optimizer:latest`
- Persistent Docker volume `solar-data` mounted at `/app/data`

Open the dashboard at `http://<lxc-ip>:8000`.

## Post-install

1. Open **Settings** and set your Home Assistant URL and long-lived token.
2. Map inverter entities, location, and battery settings.
3. Leave **SHADOW MODE** on until you trust the decisions (default).
4. Optionally set `API_TOKEN` in `/opt/solar-ai-optimizer/solar.env` on the LXC and the same value in **Settings → API security**.

No `.env` file is required at install time — the UI persists config to the data volume.

## Update

Re-run the helper script against the existing container (community-scripts update flow):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

This pulls the latest image, recreates the `solar-optimizer` container, and preserves the `solar-data` volume.

Or update manually inside the LXC:

```bash
docker pull ghcr.io/oraad/solar-ai-optimizer:latest
docker stop solar-optimizer && docker rm solar-optimizer
docker run -d --name solar-optimizer --restart unless-stopped \
  --env-file /opt/solar-ai-optimizer/solar.env \
  -v solar-data:/app/data \
  -p 8000:8000 \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

## Backup

Back up the Docker volume before upgrades:

```bash
docker run --rm -v solar-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/solar-data-backup.tar.gz -C /data .
```

Important files: `solar.db`, `config.runtime.yaml`, `model.json`.

## Troubleshooting

| Issue | Check |
|-------|--------|
| Docker won't start in LXC | Container needs `nesting=1` and `keyctl=1` (set by default in the helper script) |
| Can't reach Home Assistant | LXC must route to HA on your LAN; use HA IP instead of mDNS if needed |
| Health check fails | `docker logs solar-optimizer` inside the LXC |
| Port 8000 in use | Change host mapping in `/opt/solar-ai-optimizer/solar.env` deployment or edit the `docker run` port |

## Fork / branch

Point at your own git ref:

```bash
export SOLAR_REPO_RAW="https://raw.githubusercontent.com/you/solar-ai-optimizer/your-branch"
bash -c "$(curl -fsSL ${SOLAR_REPO_RAW}/proxmox/ct/solar-ai-optimizer.sh)"
```

## Future: Proxmox OCI native (PVE 9.1+)

Proxmox VE 9.1+ can run OCI images from GHCR as application LXCs ([official docs](https://pve.proxmox.com/pve-docs/chapter-pct.html), [tutorial](https://raymii.org/s/tutorials/Finally_run_Docker_containers_natively_in_Proxmox_9.1.html)). This feature is still a **technology preview** — updates require recreating the CT, and there is no Docker Compose support.

The published image is **OCI-ready** (exec `ENTRYPOINT`, standard labels, `VOLUME /app/data`, env-driven config). Automated OCI helper scripts will be added when Proxmox stabilizes native OCI workflows.

Manual steps for early adopters on PVE 9.1+:

1. **Storage → CT Templates → Pull from OCI Registry**  
   Reference: `ghcr.io/oraad/solar-ai-optimizer:latest`
2. **Create CT** from that template (`--ostype unmanaged`).
3. Add mount point **`mp0` → `/app/data`** (4 GB+ recommended).
4. In **Options → Environment**, set at minimum:
   - `SHADOW_MODE=true`
   - `DATA_DIR=/app/data`
   - `DATABASE_URL=sqlite+aiosqlite:////app/data/solar.db`
5. Start the CT and open `http://<ct-ip>:8000`.

Until OCI support matures, the **Docker-in-LXC** helper above is the recommended production path.

## Files

| Path | Role |
|------|------|
| [`ct/solar-ai-optimizer.sh`](ct/solar-ai-optimizer.sh) | Host script (Proxmox shell) |
| [`install/solar-ai-optimizer-install.sh`](install/solar-ai-optimizer-install.sh) | Runs inside the new LXC |
| [`lib/solar-common.sh`](lib/solar-common.sh) | Shared image/deploy helpers |
