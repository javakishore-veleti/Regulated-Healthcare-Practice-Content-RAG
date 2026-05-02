#!/usr/bin/env bash
# Stop and remove the local Regulated Healthcare RAG stack containers.
# Volumes are preserved by default; pass --volumes to also drop named volumes.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

down_args=()
if [[ "${1:-}" == "--volumes" ]]; then
  down_args+=("--volumes")
  shift
fi

# Reverse order so dependents stop before their dependencies.
services=(
  # "VectorDBs"
  # "Observability/Jaeger"
  # "Observability/Grafana"
  # "Observability/Prometheus"
  # "Airflow"
  "Postgres"
)

for svc in "${services[@]}"; do
  compose="$DIR/$svc/docker-compose.yml"
  if [[ -f "$compose" ]]; then
    echo "==> Stopping $svc"
    docker compose -f "$compose" down "${down_args[@]}"
  fi
done
