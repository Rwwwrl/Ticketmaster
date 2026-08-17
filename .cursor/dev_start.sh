#!/usr/bin/env bash
# Per-boot startup for the Ticketmaster Cloud Agent environment.
# Starts the Docker daemon (if needed), brings up Postgres + Redis, applies
# database migrations, and seeds local-dev data. Idempotent and safe to re-run.
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

echo "[start] Done. Postgres:15432 Redis:16379 ready."
