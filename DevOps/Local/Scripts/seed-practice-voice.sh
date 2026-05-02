#!/usr/bin/env bash
# Seeds the Practice_Voice_Sample corpus into rag_vectors.child_chunk_embeddings.
# Idempotent — the underlying SQL upsert uses ON CONFLICT DO NOTHING.
#
# Runs after migrations in docker-all-up.sh. The script needs the project's
# Python venv with psycopg2 available (root requirements.txt covers it). If the
# venv hasn't been provisioned yet, this step is skipped with a friendly notice
# rather than failing the whole stack-up.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DIR/../../.." && pwd)"

# shellcheck source=./_common.sh
source "$DIR/_common.sh"

if [[ ! -x "$VENV_PREFIX/bin/python" ]]; then
  echo "==> Skipping practice-voice seed: venv not provisioned at $VENV_PREFIX"
  echo "    Run 'npm run venv:install' (or DevOps/Local/Scripts/venv-install.sh) first,"
  echo "    then re-run docker-all-up.sh."
  exit 0
fi

# Default DSN parts target the rhc-postgres container's host-mapped 5432.
# Override any of these when calling outside the local docker stack.
export RHC_PG_HOST="${RHC_PG_HOST:-localhost}"
export RHC_PG_PORT="${RHC_PG_PORT:-5432}"
export RHC_PG_DB="${RHC_PG_DB:-rag_vectors}"
export RHC_PG_USER="${RHC_PG_USER:-rhc_admin}"
export RHC_PG_PASSWORD="${RHC_PG_PASSWORD:-rhc_admin_password}"

echo "==> Seeding Practice_Voice_Sample corpus"
"$VENV_PREFIX/bin/python" "$REPO_ROOT/middleware/RAGMgmt-Service/scripts/seed_practice_voice.py"
