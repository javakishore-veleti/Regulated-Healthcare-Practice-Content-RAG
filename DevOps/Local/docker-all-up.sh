#!/usr/bin/env bash
# Bring up the full local Regulated Healthcare RAG stack.
# Each service has its own docker-compose.yml in a sibling folder.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

services=(
  "Postgres"
  "Airflow"
  # "Observability/Prometheus" # TODO: image not cached locally
  # "Observability/Grafana"    # TODO: image not cached locally
  # "Observability/Jaeger"     # TODO: image not cached locally
  # "VectorDBs"                # TODO: image not cached locally
)

for svc in "${services[@]}"; do
  compose="$DIR/$svc/docker-compose.yml"
  if [[ -f "$compose" ]]; then
    echo "==> Bringing up $svc"
    docker compose -f "$compose" up -d --wait
  else
    echo "==> Skipping $svc (no docker-compose.yml yet)"
  fi
done

echo
echo "==> Running database migrations"
"$DIR/Postgres/run-migrations.sh"

echo
echo "Stack is up. Run docker-all-status.sh to verify."
