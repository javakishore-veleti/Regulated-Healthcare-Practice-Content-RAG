#!/usr/bin/env bash
# `npm run venv:install` — install requirements.txt into the conda venv.
# Creates the venv first if missing.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/_common.sh"
ensure_venv
ensure_requirements
echo "Installed requirements into: $VENV_PREFIX"
