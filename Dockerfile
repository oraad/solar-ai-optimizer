# Single-image build: compiles the Lit dashboard, then serves it together with
# the FastAPI backend from one Python 3.14 container.

# ---- Stage 1: build the frontend ----
FROM node:24-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: backend + bundled dashboard ----
FROM python:3.14-slim AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STATIC_DIR=/app/static \
    CONFIG_PATH=/app/config/config.yaml \
    DATA_DIR=/app/data \
    DATABASE_URL=sqlite+aiosqlite:////app/data/solar.db

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-extras.txt ./
ARG INSTALL_EXTRAS=1
RUN pip install --upgrade pip && pip install -r requirements.txt \
    && if [ "$INSTALL_EXTRAS" = "1" ]; then pip install -r requirements-extras.txt; fi

COPY VERSION ./VERSION
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY config/config.yaml.example ./config/config.yaml
COPY run.sh ./run.sh
COPY --from=frontend /ui/dist ./static

# Normalize line endings (Windows checkouts use CRLF, which breaks the shebang)
# and make the entrypoint executable.
RUN sed -i 's/\r$//' /app/run.sh && chmod +x /app/run.sh && mkdir -p /app/data

# Persistent state (SQLite DB, runtime config, learned models). Mount at deploy time.
VOLUME ["/app/data"]

EXPOSE 8000

# OCI / Proxmox application-container metadata (see proxmox/README.md).
LABEL org.opencontainers.image.title="Solar AI Optimizer" \
      org.opencontainers.image.description="Resilience-first solar/battery optimizer for Home Assistant" \
      org.opencontainers.image.source="https://github.com/oraad/solar-ai-optimizer" \
      org.opencontainers.image.url="https://github.com/oraad/solar-ai-optimizer" \
      org.opencontainers.image.licenses="MIT" \
      io.oraad.solar.data-dir="/app/data" \
      io.oraad.solar.http-port="8000" \
      io.oraad.solar.health-path="/api/health"

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# Universal entrypoint: docker-compose, HA add-on, and future Proxmox OCI.
# Translates /data/options.json into env vars when present (add-on mode).
ENTRYPOINT ["/app/run.sh"]

# ---- Stage 3: test runner ----
FROM app AS test
COPY backend/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY VERSION ./VERSION
COPY scripts ./scripts
COPY config.yaml ./config.yaml
COPY frontend/package.json ./frontend/package.json
COPY backend/tests ./tests
ENV PYTHONPATH=/app
WORKDIR /app
# Clear production entrypoint so CMD runs pytest (not uvicorn via run.sh).
ENTRYPOINT []
CMD ["python", "-m", "pytest", "tests/", "-q"]

# Default image for `docker build` and HA add-on (no --target). Must stay last.
FROM app
