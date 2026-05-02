#!/usr/bin/env bash
# `npm run datamgmt:start` — ensure venv + deps, then start DataMgmt-Service
# on $API_PORT (default 8001). Pre-flight: creates the venv and installs
# requirements.txt if missing or stale.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/_common.sh"
require_in_venv

SERVICE_DIR="$REPO_ROOT/middleware/DataMgmt-Service"
HOST="${API_HOST:-0.0.0.0}"
PORT="${DATAMGMT_PORT:-8001}"

cd "$SERVICE_DIR"
exec "$VENV_UVICORN" main:app --host "$HOST" --port "$PORT" --reload
