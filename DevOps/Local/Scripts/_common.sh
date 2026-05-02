#!/usr/bin/env bash
# Shared helpers for the conda-venv developer workflow. Sourced by every script
# under DevOps/Local/Scripts/. Defines:
#   $VENV_PREFIX   — absolute path to the conda venv (path-prefixed env)
#   $VENV_PYTHON   — path to the venv's python binary
#   $VENV_UVICORN  — path to the venv's uvicorn binary
#   $REPO_ROOT     — absolute repo root
# Plus:
#   require_conda     — prints help and exits if conda isn't on PATH
#   ensure_venv       — creates the venv if missing
#   ensure_requirements — installs requirements.txt into the venv
#   require_in_venv   — confirms VENV_PYTHON exists; runs ensure_venv if not

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VENV_PREFIX="${VENV_PREFIX:-$HOME/runtime_data/python_venvs/RHPContent-RAG}"
VENV_PYTHON="$VENV_PREFIX/bin/python"
VENV_UVICORN="$VENV_PREFIX/bin/uvicorn"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
REQUIREMENTS_FILE="$REPO_ROOT/requirements.txt"

require_conda() {
  if ! command -v conda >/dev/null 2>&1; then
    cat >&2 <<EOF
ERROR: 'conda' not found on PATH.
Install Miniconda from https://docs.conda.io/en/latest/miniconda.html
or Anaconda, then re-run this script.
EOF
    exit 1
  fi
}

ensure_venv() {
  require_conda
  if [[ -x "$VENV_PYTHON" ]]; then
    return 0
  fi
  echo "==> Creating conda venv at $VENV_PREFIX (python=$PYTHON_VERSION)"
  mkdir -p "$(dirname "$VENV_PREFIX")"
  conda create --yes --quiet --prefix "$VENV_PREFIX" "python=$PYTHON_VERSION"
}

ensure_requirements() {
  if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    echo "ERROR: requirements file not found at $REQUIREMENTS_FILE" >&2
    exit 1
  fi
  echo "==> Installing $REQUIREMENTS_FILE into $VENV_PREFIX"
  "$VENV_PYTHON" -m pip install --upgrade pip >/dev/null
  "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE"
}

require_in_venv() {
  ensure_venv
  if [[ ! -x "$VENV_UVICORN" ]] || [[ ! -x "$VENV_PYTHON" ]]; then
    ensure_requirements
    return 0
  fi
  # Cheap drift check: re-install if requirements.txt is newer than the venv.
  if [[ "$REQUIREMENTS_FILE" -nt "$VENV_PREFIX/conda-meta/history" ]]; then
    echo "==> requirements.txt is newer than venv; re-running pip install"
    ensure_requirements
  fi
}
