#!/usr/bin/env bash
# `npm run ragmgmt:start` — ensure venv + deps, then start RAGMgmt-Service
# on $RAGMGMT_PORT (default 8002). Pre-flight: creates the venv and installs
# requirements.txt if missing or stale.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/_common.sh"
require_in_venv

SERVICE_DIR="$REPO_ROOT/middleware/RAGMgmt-Service"
HOST="${API_HOST:-0.0.0.0}"
PORT="${RAGMGMT_PORT:-8002}"

cd "$SERVICE_DIR"
exec "$VENV_UVICORN" main:app --host "$HOST" --port "$PORT" --reload
