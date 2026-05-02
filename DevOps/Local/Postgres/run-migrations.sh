#!/usr/bin/env bash
# Liquibase-style migration runner.
# Discovers SQL files under middleware/<service>/migrations/<db_name>/V*.sql, sorts lexically per DB,
# applies pending ones inside the rhc-postgres container, and tracks applied filenames + sha256 in a
# _schema_migrations table per target database.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DIR/../../.." && pwd)"
PG_CONTAINER="${PG_CONTAINER:-rhc-postgres}"
PG_USER="${POSTGRES_USER:-rhc_admin}"

if ! docker ps --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
  echo "ERROR: Postgres container '${PG_CONTAINER}' is not running. Run docker-all-up.sh first." >&2
  exit 1
fi

if ! docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" -d postgres -q 2>/dev/null; then
  echo "ERROR: Postgres in '${PG_CONTAINER}' is not accepting connections yet." >&2
  exit 1
fi

ensure_migrations_table() {
  local db="$1"
  docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$db" -v ON_ERROR_STOP=1 -q <<'SQL' >/dev/null
CREATE TABLE IF NOT EXISTS _schema_migrations (
    filename    TEXT        PRIMARY KEY,
    checksum    TEXT        NOT NULL,
    applied_dt  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SQL
}

is_applied() {
  local db="$1" rel="$2"
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$db" -tAq -c \
    "SELECT 1 FROM _schema_migrations WHERE filename = '$rel'" 2>/dev/null | tr -d '[:space:]'
}

apply_one() {
  local db="$1" file="$2" rel="$3" checksum="$4"
  docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$db" -v ON_ERROR_STOP=1 -q < "$file" >/dev/null
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$db" -v ON_ERROR_STOP=1 -q -c \
    "INSERT INTO _schema_migrations (filename, checksum) VALUES ('$rel', '$checksum')" >/dev/null
}

run_for_db() {
  local db="$1"
  local files
  files=$(find "$REPO_ROOT/middleware" -path "*/migrations/$db/V*.sql" -type f 2>/dev/null | sort)

  if [[ -z "$files" ]]; then
    return 0
  fi

  echo "==> Migrating database: $db"
  ensure_migrations_table "$db"

  while IFS= read -r mig; do
    [[ -z "$mig" ]] && continue
    local rel="${mig#$REPO_ROOT/}"
    local checksum
    checksum=$(shasum -a 256 "$mig" | awk '{print $1}')

    if [[ "$(is_applied "$db" "$rel")" == "1" ]]; then
      echo "  [skip ] $rel"
      continue
    fi

    echo "  [apply] $rel"
    apply_one "$db" "$mig" "$rel" "$checksum"
  done <<< "$files"
}

# Discover unique target DB names from migration folder structure.
db_names=$(find "$REPO_ROOT/middleware" -type d -name 'migrations' 2>/dev/null \
           | while read -r m; do find "$m" -mindepth 1 -maxdepth 1 -type d 2>/dev/null; done \
           | xargs -I{} -n1 basename "{}" 2>/dev/null \
           | sort -u)

if [[ -z "$db_names" ]]; then
  echo "No migrations found under middleware/*/migrations/."
  exit 0
fi

for db in $db_names; do
  run_for_db "$db"
done

echo
echo "Migrations complete."
