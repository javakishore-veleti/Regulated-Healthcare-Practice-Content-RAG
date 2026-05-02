#!/usr/bin/env bash
# Run DataMgmt-Service locally on the host (the FastAPI runtime is not containerized in this slice
# because no cached Python image is available — adding one would violate the no-extra-pulls rule).
# Requires: uv (https://docs.astral.sh/uv/) and a running rhc-postgres (./DevOps/Local/docker-all-up.sh).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' not found on PATH. Install from https://docs.astral.sh/uv/." >&2
  exit 1
fi

uv sync
exec uv run uvicorn main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8001}" --reload
