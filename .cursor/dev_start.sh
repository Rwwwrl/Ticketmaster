#!/usr/bin/env bash
# Per-boot startup for the Ticketmaster Cloud Agent environment.
# Starts the Docker daemon (if needed), brings up Postgres + Redis, applies
# database migrations, seeds local-dev data, and launches the backend + frontend
# dev servers. Idempotent and safe to re-run: already-running pieces are skipped.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "[start] Ensuring the Docker daemon is running"
if ! sudo docker info >/dev/null 2>&1; then
  sudo mkdir -p /etc/docker
  echo '{ "storage-driver": "fuse-overlayfs", "iptables": false, "bridge": "none" }' | sudo tee /etc/docker/daemon.json >/dev/null
  sudo nohup dockerd >/tmp/dockerd.log 2>&1 &
  for _ in $(seq 1 30); do
    if sudo docker info >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi
sudo docker info >/dev/null 2>&1 || { echo "[start] Docker daemon failed to start"; cat /tmp/dockerd.log; exit 1; }

echo "[start] Bringing up Postgres + Redis (docker compose)"
sudo docker compose -f docker-compose.yaml -p ticketmaster up -d

echo "[start] Waiting for Postgres + Redis to become healthy"
for _ in $(seq 1 60); do
  pg="$(sudo docker inspect -f '{{.State.Health.Status}}' postgres 2>/dev/null || echo starting)"
  rd="$(sudo docker inspect -f '{{.State.Health.Status}}' redis 2>/dev/null || echo starting)"
  if [ "$pg" = healthy ] && [ "$rd" = healthy ]; then break; fi
  sleep 2
done
[ "$(sudo docker inspect -f '{{.State.Health.Status}}' postgres 2>/dev/null)" = healthy ] || { echo "[start] Postgres not healthy"; exit 1; }
[ "$(sudo docker inspect -f '{{.State.Health.Status}}' redis 2>/dev/null)" = healthy ] || { echo "[start] Redis not healthy"; exit 1; }

echo "[start] Applying database migrations"
poetry -C "$REPO_ROOT" run alembic -c "$REPO_ROOT/src/ticketmaster/alembic.ini" upgrade heads

echo "[start] Seeding local-dev data (idempotent)"
poetry -C "$REPO_ROOT" run python scripts/seed_dev_data.py

# Launch the backend (FastAPI) unless it is already listening on :8080.
if ! curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then
  echo "[start] Launching backend (FastAPI) on :8080"
  nohup poetry -C "$REPO_ROOT" run fastapi dev src/ticketmaster/ticketmaster/http/main.py --no-reload --port 8080 \
    >/tmp/backend.log 2>&1 &
  for _ in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi

# Launch the frontend (Vite) unless it is already listening on :5173.
if ! curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1; then
  echo "[start] Launching frontend (Vite) on :5173"
  nohup bash -lc "cd '$REPO_ROOT/frontend' && npm run dev -- --host 0.0.0.0" \
    >/tmp/frontend.log 2>&1 &
  for _ in $(seq 1 30); do
    if curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi

curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1 && echo "[start] Backend ready:  http://localhost:8080" || echo "[start] WARNING: backend not responding"
curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1 && echo "[start] Frontend ready: http://localhost:5173" || echo "[start] WARNING: frontend not responding"
echo "[start] Done."
