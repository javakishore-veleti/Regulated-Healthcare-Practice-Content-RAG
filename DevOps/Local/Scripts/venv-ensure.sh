#!/usr/bin/env bash
# `npm run venv:ensure` — create the conda venv at the canonical path if missing.
# Idempotent: no-op when the venv already exists. Does NOT install requirements
# (use `venv:install` for that, or `services:start` which does both).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/_common.sh"
ensure_venv
echo "Conda venv ready at: $VENV_PREFIX"
