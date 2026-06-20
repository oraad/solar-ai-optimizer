# Proxmox deployment

Deploy **Solar AI Optimizer** on Proxmox VE using a [community-scripts](https://github.com/community-scripts/ProxmoxVE)-style helper that creates a Debian LXC, installs Docker, and runs the published GHCR image.

For other install paths see [Installation](installation.md).

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

The install script writes `/opt/solar-ai-optimizer/solar.env` with `TRUST_INGRESS_HEADERS=true` (for Home Assistant ingress) and auto-generated local admin credentials. The username and password are printed once at the end of the install — save them.

## Post-install

1. **Save the local admin password** shown at install completion (username defaults to `admin`). Use it to sign in at `http://<lxc-ip>:8000` when not using HA ingress.
2. Open **Settings** and set your [Home Assistant URL and long-lived token](home-assistant-setup.md#long-lived-access-token).
3. Map inverter entities, location, and battery settings.
4. Leave **SHADOW MODE** on until you trust the decisions (default).
5. Optionally set `API_TOKEN` in `/opt/solar-ai-optimizer/solar.env` on the LXC and the same value in **Settings → API security**.

Re-running the update helper on an install that already has local admin credentials does **not** rotate the password. To change it manually, generate a new bcrypt hash per [Ingress and authorization](ingress-auth.md) and edit `solar.env`.

## Update

Re-run the helper script against the existing container (community-scripts update flow):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

This pulls the latest image, recreates the `solar-optimizer` container, and preserves the `solar-data` volume. It also migrates older installs: if `TRUST_INGRESS_HEADERS` or local admin credentials are missing from `solar.env`, they are added automatically and any new password is shown once.

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

Proxmox VE 9.1+ can run OCI images from GHCR as application LXCs. This feature is still a
**technology preview** — updates require recreating the CT, and there is no Docker Compose support.

The published image is **OCI-ready** (exec `ENTRYPOINT`, standard labels, `VOLUME /app/data`, env-driven config).

Manual steps for early adopters on PVE 9.1+:

1. **Storage → CT Templates → Pull from OCI Registry** — `ghcr.io/oraad/solar-ai-optimizer:latest`
2. **Create CT** from that template (`--ostype unmanaged`).
3. Add mount point **`mp0` → `/app/data`** (4 GB+ recommended).
4. In **Options → Environment**, set at minimum:
   - `SHADOW_MODE=true`
   - `DATA_DIR=/app/data`
   - `DATABASE_URL=sqlite+aiosqlite:////app/data/solar.db`
5. Start the CT and open `http://<ct-ip>:8000`.

Until OCI support matures, the **Docker-in-LXC** helper above is the recommended production path.

## Repository files

| Path | Role |
|------|------|
| [`proxmox/ct/solar-ai-optimizer.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/ct/solar-ai-optimizer.sh) | Host script (Proxmox shell) |
| [`proxmox/install/solar-ai-optimizer-install.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/install/solar-ai-optimizer-install.sh) | Runs inside the new LXC |
| [`proxmox/lib/solar-common.sh`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/lib/solar-common.sh) | Shared image/deploy helpers |

The canonical copy of this guide lives on the [documentation site](https://oraad.github.io/solar-ai-optimizer/proxmox/). The repository also keeps [`proxmox/README.md`](https://github.com/oraad/solar-ai-optimizer/blob/main/proxmox/README.md) for GitHub browsing.
