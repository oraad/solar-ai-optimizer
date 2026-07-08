# Proxmox deployment

> Published copy: [documentation site → Proxmox Deployment](https://oraad.github.io/solar-ai-optimizer/proxmox/)

Deploy **Solar AI Optimizer** on Proxmox VE using a [community-scripts](https://github.com/community-scripts/ProxmoxVE)-style helper that creates an LXC (Debian or Alpine), installs Docker, and runs the published GHCR image.

## Quick install (Debian)

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

**Home Assistant:** Install the [HACS integration](https://oraad.github.io/solar-ai-optimizer/home-assistant-integration/) for fail-safe and Update entities. Generate a pairing code in Solar Settings, then add the integration in HA (Core 2026.7.0+).

The install script writes `/opt/solar-ai-optimizer/solar.env` with `TRUST_INGRESS_HEADERS=true` (trusts HA ingress user headers and sets `X-Frame-Options: SAMEORIGIN` for the sidebar panel) and auto-generated local admin credentials. The username and password are printed once at the end of the install — save them.

## Quick install (Alpine)

For a smaller LXC base OS, use the Alpine helper instead:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer-alpine.sh)"
```

The Alpine wizard provisions:

- Alpine 3.23 LXC (4 GB disk by default) with **nesting** and **keyctl**
- Docker Engine via `apk` (OpenRC service, `json-file` log driver)
- Same `solar-optimizer` container and `solar-data` volume as the Debian path

Use the **Alpine script for updates** on Alpine installs (the in-LXC `update` command points at the matching script automatically).

## Post-install

1. **Save the local admin password** shown at install completion (username defaults to `admin`). Use it to sign in at `http://<lxc-ip>:8000` when not using HA ingress.
2. Open **Settings** and set your Home Assistant URL and long-lived token.
3. Map inverter entities, location, and battery settings.
4. Leave **SHADOW MODE** on until you trust the decisions (default).
5. Optionally set `API_TOKEN` in `/opt/solar-ai-optimizer/solar.env` on the LXC and the same value in **Settings → API security**.

Re-running the update helper on an install that already has local admin credentials does **not** rotate the password. To reset the password:

```bash
bash /opt/solar-ai-optimizer/reset-local-password.sh
```

Or run `solar_reset_local_password` after sourcing `proxmox/lib/solar-common.sh`. See [Ingress and authorization](../docs/ingress-auth.md#reset-local-admin-password).

## Update

Re-run the helper script you used for install against the existing container (community-scripts update flow).

**Debian LXC:**

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

**Alpine LXC:**

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer-alpine.sh)"
```

This pulls the latest image, recreates the `solar-optimizer` container, and preserves the `solar-data` volume. It also migrates older installs: if `TRUST_INGRESS_HEADERS` or local admin credentials are missing from `solar.env`, they are added automatically and any new password is shown once. Each update run also rewrites `/usr/bin/update` to point at this repository (fixes older installs that pointed at community-scripts).

From **inside the LXC**, you can also run:

```bash
update
```

That command runs the same Solar helper script. Helper functions are vendored under [`vendor/community-scripts/`](vendor/community-scripts/) and loaded via `SOLAR_REPO_RAW` at runtime.

Or update manually inside the LXC (include the Docker socket and self-update flags so
**Settings → Software updates → Update now** keeps working):

```bash
docker pull ghcr.io/oraad/solar-ai-optimizer:latest
docker stop solar-optimizer && docker rm solar-optimizer
docker run -d --name solar-optimizer --restart unless-stopped \
  --env-file /opt/solar-ai-optimizer/solar.env \
  -v solar-data:/app/data \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e SELF_UPDATE_ENABLED=true \
  -e SELF_UPDATE_ENV_FILE=/opt/solar-ai-optimizer/solar.env \
  -e SELF_UPDATE_IMAGE=ghcr.io/oraad/solar-ai-optimizer:latest \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

Prefer the `update` command or host-side helper script — same pull-and-recreate flow, less error-prone.

### Dashboard one-click update

New Proxmox installs mount the Docker socket and set `SELF_UPDATE_ENABLED=true` on the
`solar-optimizer` container. Admins can open **Settings → Software updates** to see release
notes and click **Update now** (same pull-and-recreate flow as `update`).

!!! warning "Docker socket access"
    Mounting `/var/run/docker.sock` grants effective root on the LXC. The update API is
    admin-only, but only enable this on hosts you trust. Re-run the install/update helper
    script to apply the socket mount on older LXC installs.

One-click update requires **v0.5.5 or newer** (the image includes the Docker CLI via the
`docker-cli` package). v0.5.2–0.5.4 images on Debian Trixie installed `docker.io`, which
no longer provides `/usr/bin/docker`. If you see *"Docker CLI is not available in this
container"*, pull **v0.5.5+** and recreate (`update` or the manual `docker run` above).

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
| *Docker CLI is not available in this container* (Settings → Software updates) | Fixed in **v0.5.5+** (`docker-cli` in the image). On v0.5.2–0.5.4, `docker exec solar-optimizer command -v docker` is empty even after recreate. Run `update` after pulling v0.5.5+, or recreate with the full manual `docker run` flags (socket + `SELF_UPDATE_*` env). |
| Sidebar panel blank / `X-Frame-Options: deny` | `TRUST_INGRESS_HEADERS=true` in `/opt/solar-ai-optimizer/solar.env`; ingress `url` must point to `http://<lxc-ip>:8000` (not your HA URL); update to a current image and reload ingress in HA |
| Docker won't start in LXC | Container needs `nesting=1` and `keyctl=1` (set by default in the helper script); on Alpine also check `rc-service docker status` |
| Can't reach Home Assistant | LXC must route to HA on your LAN; use HA IP instead of mDNS if needed |
| Health check fails | `docker logs solar-optimizer` inside the LXC |
| Port 8000 in use | Change host mapping in `/opt/solar-ai-optimizer/solar.env` deployment or edit the `docker run` port |

## Fork / branch

Point at your own git ref:

```bash
export SOLAR_REPO_RAW="https://raw.githubusercontent.com/you/solar-ai-optimizer/your-branch"
bash -c "$(curl -fsSL ${SOLAR_REPO_RAW}/proxmox/ct/solar-ai-optimizer.sh)"          # Debian
bash -c "$(curl -fsSL ${SOLAR_REPO_RAW}/proxmox/ct/solar-ai-optimizer-alpine.sh)"   # Alpine
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
| [`ct/solar-ai-optimizer.sh`](ct/solar-ai-optimizer.sh) | Host script — Debian LXC (default) |
| [`ct/solar-ai-optimizer-alpine.sh`](ct/solar-ai-optimizer-alpine.sh) | Host script — Alpine LXC |
| [`install/solar-ai-optimizer-install.sh`](install/solar-ai-optimizer-install.sh) | Runs inside the new LXC |
| [`lib/solar-common.sh`](lib/solar-common.sh) | Shared image/deploy helpers |
| [`vendor/community-scripts/`](vendor/community-scripts/) | Vendored community-scripts helpers (pinned upstream) |
