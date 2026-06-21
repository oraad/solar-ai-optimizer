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

## Docker Compose (recommended)

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

Optional environment overrides go in `docker-compose.yml` `environment:` or an `.env` file
(see [Configuration](configuration.md)).

### Dashboard updates (optional)

Admins can check for new releases under **Settings → Software updates**. The panel shows
the current version, latest GitHub release notes, and manual upgrade steps.

To enable **one-click updates** from the dashboard (pull image and recreate the container),
use the self-update overlay. This mounts the host Docker socket into the app container —
only use on trusted homelab hosts:

```bash
docker compose -f docker-compose.yml -f docker-compose.self-update.yml up -d
```

!!! note "Image version"
    One-click update requires **v0.5.2 or newer** (the image includes the Docker CLI).
    If you enabled self-update on an older GHCR image, run `docker pull` and recreate
    the container once manually before using **Update now** in the dashboard.

---

## Docker (standalone image)

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

---

## Home Assistant add-on

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

## Proxmox LXC

!!! info "One-liner on Proxmox VE"
    Community-scripts-style helper creates a Debian or Alpine LXC with Docker-in-LXC
    (nesting + keyctl), pulls the GHCR image, and exposes port 8000.

**Prerequisites:** Proxmox VE host with root shell access.

On the **Proxmox host** (Debian LXC — default):

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
3. Set **latitude / longitude** and **PV arrays** (required for solar forecast)
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
cd frontend && npm run docs:screenshots
```

See [Dashboard user guide → Regenerating screenshots](frontend-manual.md#regenerating-screenshots).

### Reset local admin password

When local login is enabled, reset credentials from the repo root:

```bash
./scripts/reset-local-password.sh
```

See [Ingress and authorization → Reset local admin password](ingress-auth.md#reset-local-admin-password).
