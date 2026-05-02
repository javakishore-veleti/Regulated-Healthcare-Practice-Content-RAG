#!/usr/bin/env bash
# Show the status of every service in the local Regulated Healthcare RAG stack.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

services=(
  "Postgres"
  # "Airflow"
  # "Observability/Prometheus"
  # "Observability/Grafana"
  # "Observability/Jaeger"
  # "VectorDBs"
)

for svc in "${services[@]}"; do
  compose="$DIR/$svc/docker-compose.yml"
  if [[ -f "$compose" ]]; then
    echo "==> $svc"
    docker compose -f "$compose" ps
    echo
  fi
done
