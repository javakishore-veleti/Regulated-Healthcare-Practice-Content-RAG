#!/usr/bin/env bash
# `npm run venv:show-activate` — print the activate command users can copy/paste
# into a fresh shell. (npm scripts can't activate in the parent shell themselves.)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/_common.sh"

cat <<EOF
# To activate the venv in your current shell, run:
conda activate "$VENV_PREFIX"

# To deactivate later:
conda deactivate
EOF
