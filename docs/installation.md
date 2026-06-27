# Installation and quick start

Solar AI Optimizer ships as a single Docker image. Choose the deployment path that
fits your environment — all paths serve the dashboard and API on **port 8000** and
start in **shadow mode** (observe-only; no inverter writes until you switch to live).

!!! warning "Shadow mode first"
    Every path defaults to **SHADOW MODE**. Watch decisions for a day or two before
    enabling live control from the dashboard **Overrides** panel.

## Choose your deployment

| Method | Best for | Persistence |
|--------|----------|-------------|
| [Docker Compose](#docker-compose-recommended) | Dev, homelab, generic Docker host | `solar-data` volume |
| [Docker (GHCR image)](#docker-standalone-image) | Single container, no Compose | `solar-data` volume |
| [Home Assistant add-on](#home-assistant-add-on) | HAOS / Supervised | Supervisor `/data` |
| [Proxmox LXC](#proxmox-lxc) | Proxmox VE homelab | Docker volume inside LXC |

See also: [Home Assistant setup](home-assistant-setup.md) · [Configuration](configuration.md) · [`.env.example`](https://github.com/oraad/solar-ai-optimizer/blob/main/.env.example)

---

## Docker Compose (recommended) {#docker-compose-recommended}

!!! tip "Recommended for most users"
    One command, persistent config, and easy upgrades. No `.env` or `config.yaml` required —
    configure everything from the dashboard **Settings** panel.

**Prerequisites:** Docker Engine with Compose v2.

```bash
git clone https://github.com/oraad/solar-ai-optimizer.git
cd solar-ai-optimizer
docker compose up -d --build
```

Open **http://localhost:8000**.

To run backend or frontend tests:

```bash
docker compose run --rm test
docker compose run --rm frontend-test
```

**Local pytest (without Docker):** requires **Python 3.14+** (`bash scripts/check-python.sh`).
From `backend/`, install `requirements.txt` + `requirements-dev.txt`, then run
`python -m pytest tests/ -q`. This matches CI when using the repo's dev dependencies.
On Windows, if you have `pytest-homeassistant-custom-component` installed globally for HA
custom-component work, it can block asyncio sockets and cause `SocketBlockedError` or
`ProactorEventLoop ... _ssock` errors. This project's `pytest.ini` disables that
plugin automatically; you can also uninstall it or pass `-p no:homeassistant`.

Optional environment overrides go in `docker-compose.yml` `environment:` or an `.env` file
(see [Configuration](configuration.md)).

### Dashboard updates (optional)

Admins can check for new releases under **Settings → Software updates**. The panel lists
recent stable releases with formatted release notes. On Docker self-update hosts, pick
**Install** on any version (upgrade or downgrade); a data backup is created automatically
before each install. Use **Restore** in the backups section if an install fails.

To enable **one-click updates** from the dashboard (pull image and recreate the container),
use the self-update overlay. This mounts the host Docker socket into the app container —
only use on trusted homelab hosts:

```bash
docker compose -f docker-compose.yml -f docker-compose.self-update.yml up -d
```

Each install pins `SELF_UPDATE_IMAGE` to the selected tag (e.g. `ghcr.io/oraad/solar-ai-optimizer:0.5.8`).
To track `:latest` again, install the newest release from the picker or set the env var manually
when recreating the container.

The Settings panel shows step-by-step progress (including image pull %). The service is
**briefly offline** during the container swap; if the new version fails its health check,
the previous container is restored automatically. On failure, check
`/app/data/.update-logs/latest.log` on the data volume.

!!! note "Image version"
    One-click install requires **v0.5.5 or newer** (the image includes the Docker CLI via
    `docker-cli`). Releases below v0.5.5 cannot be installed via the dashboard picker.
    If you enabled self-update on v0.5.2–0.5.4, run `docker pull` and recreate the container
    once manually before using the version picker.

---

## Docker (standalone image) {#docker-standalone-image}

!!! info "Pre-built image"
    Use this when you do not want Docker Compose. The same GHCR image powers every deployment path.

**Prerequisites:** Docker Engine.

Pull and run:

```bash
docker pull ghcr.io/oraad/solar-ai-optimizer:latest

docker run -d --name solar-optimizer --restart unless-stopped \
  -v solar-data:/app/data \
  -p 8000:8000 \
  -e SHADOW_MODE=true \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

Build locally:

```bash
docker build -t solar-ai-optimizer .
docker run -d --name solar-optimizer --restart unless-stopped \
  -v solar-data:/app/data \
  -p 8000:8000 \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

Open **http://localhost:8000**. API docs: **http://localhost:8000/docs**.

For **dashboard one-click updates** on a standalone host (no Compose), include the Docker
socket, self-update flags, and a health check:

```bash
docker run -d --name solar-optimizer --restart unless-stopped \
  -v solar-data:/app/data \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e SHADOW_MODE=true \
  -e SELF_UPDATE_ENABLED=true \
  -e SELF_UPDATE_IMAGE=ghcr.io/oraad/solar-ai-optimizer:latest \
  --health-cmd="curl -fsS http://localhost:8000/api/health || exit 1" \
  --health-interval=30s --health-timeout=5s --health-retries=3 --health-start-period=25s \
  ghcr.io/oraad/solar-ai-optimizer:latest
```

Dashboard **Install** recreates the container from its current Docker configuration
(ports, volumes, networks, environment variables), similar to how Watchtower preserves
runtime overrides when updating an image. Custom `docker run` or Compose options are kept
as long as the container was created with them.

---

## Home Assistant add-on {#home-assistant-add-on}

!!! tip "Best Home Assistant integration"
    Native ingress panel, automatic Supervisor token, and no manual HA URL wiring when
    credentials are left empty in add-on options.

**Prerequisites:** Home Assistant OS or Supervised installation with add-on store access.

1. **Supervisor → Add-on store → Repositories** → add:
   ```
   https://github.com/oraad/solar-ai-optimizer
   ```
2. Install **Solar AI Optimizer** from the store.
3. Start the add-on and open the **ingress panel** from the HA sidebar (icon: solar panel).

The add-on builds from the repository `Dockerfile` and persists state under `/data`
(database, runtime config, learned model). Add-on options map to environment variables
via `run.sh` (shadow mode, log level, Solcast keys, API token, etc.).

Full HA wiring (entities, packages, ingress auth): [Home Assistant setup](home-assistant-setup.md).

---

## Proxmox LXC {#proxmox-lxc}

!!! info "One-liner on Proxmox VE"
    Community-scripts-style helper creates a Debian or Alpine LXC with Docker-in-LXC
    (nesting + keyctl), pulls the GHCR image, and exposes port 8000.

**Prerequisites:** Proxmox VE host with root shell access.

On the **Proxmox host** (Debian 13 Trixie LXC — default):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer.sh)"
```

Or for a smaller Alpine LXC base:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main/proxmox/ct/solar-ai-optimizer-alpine.sh)"
```

Open **http://&lt;lxc-ip&gt;:8000**.

Updates, backups, fork/branch overrides, and future OCI notes:
[Proxmox deployment](proxmox.md).

---

## Post-install checklist

After any deployment path:

1. Open the dashboard → **Settings**
2. **Connect Home Assistant** (URL + long-lived token) — skip if using the add-on with default Supervisor wiring
3. Set **site latitude / longitude** and **PV arrays** (required for solar forecast)
4. Map **inverter read/write entities** in Settings → Inverter entity map
5. Leave **shadow mode** on; confirm Overview decisions look reasonable
6. Optionally import the [fail-safe HA package](home-assistant-failsafe.md) and enable heartbeat in Settings → Fail-safe
7. Switch to **live** control only when you trust the optimizer

Next steps:

- [Dashboard user guide](frontend-manual.md) — tab-by-tab walkthrough
- [Roles and access](ingress-auth.md) — admin vs viewer
- [Home Assistant setup](home-assistant-setup.md) — tokens, packages, entity discovery

---

## Demo mode (documentation / screenshots only)

!!! danger "Never use in production"
    `DEMO_MODE` injects synthetic telemetry and reports HA as connected for screenshot
    and documentation workflows. Do **not** enable on a system that controls a real inverter.

For maintainers regenerating dashboard screenshots:

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
docker compose exec solar python -m scripts.seed_demo
docker compose restart solar
docker compose --profile docs run --rm docs-screenshots npm ci   # once, or after lockfile changes
docker compose --profile docs run --rm docs-screenshots
```

See [Dashboard user guide → Regenerating screenshots](frontend-manual.md#regenerating-screenshots).

### Reset local admin password

When local login is enabled, reset credentials from the repo root:

```bash
./scripts/reset-local-password.sh
```

See [Ingress and authorization → Reset local admin password](ingress-auth.md#reset-local-admin-password).
