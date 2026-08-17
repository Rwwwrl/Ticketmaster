#!/usr/bin/env bash
# Idempotent repository bootstrap for the Ticketmaster Cloud Agent environment.
# Runs after the repo is checked out. Prepares Python + Node dependencies and
# the gitignored local-dev config files. Safe to run repeatedly.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "[install] Python: pinning the workspace virtualenv to 3.14"
poetry env use python3.14

echo "[install] Python: installing workspace dependencies (path deps -> working tree)"
poetry install

echo "[install] Frontend: installing npm dependencies"
npm --prefix frontend ci

echo "[install] Backend: writing local-dev config (src/ticketmaster/env.dev.yaml)"
if [ ! -f src/ticketmaster/env.dev.yaml ]; then
  cat > src/ticketmaster/env.dev.yaml <<'YAML'
environment: dev
secret: local-dev-secret
log_level: info

postgres_db_url: postgresql+asyncpg://postgres:postgres@localhost:15432/ticketmaster
redis_url: redis://localhost:16379/0

aws_region: eu-central-1

jwt_audience: ticketmaster-backend

lambda_jwt_kms_key_arn: arn:aws:kms:eu-central-1:000000000000:key/test-placeholder
lambda_jwt_issuer: ticketmaster-cognito-pre-signup

admin_jwt_kms_key_arn: arn:aws:kms:eu-central-1:000000000000:key/test-admin-placeholder
admin_jwt_issuer: ticketmaster-admin

cognito_audience: ticketmaster-cognito-client-id
YAML
fi

echo "[install] Frontend: writing local-dev runtime config (frontend/public/config.js)"
if [ ! -f frontend/public/config.js ]; then
  cp frontend/public/config.example.js frontend/public/config.js
fi

echo "[install] Done."
