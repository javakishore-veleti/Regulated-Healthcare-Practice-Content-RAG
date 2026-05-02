#!/usr/bin/env bash
# `npm run venv:remove` — destroys the conda venv directory.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/_common.sh"

if [[ ! -d "$VENV_PREFIX" ]]; then
  echo "Nothing to remove — $VENV_PREFIX does not exist."
  exit 0
fi

if [[ "${FORCE:-}" != "1" ]]; then
  read -r -p "Remove $VENV_PREFIX ? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "Aborted."; exit 1; }
fi

rm -rf "$VENV_PREFIX"
echo "Removed $VENV_PREFIX"
