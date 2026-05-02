#!/usr/bin/env bash
# Stop and remove the local Regulated Healthcare RAG stack containers AND named volumes.
# Volume removal is the DEFAULT (clean reset on every down). Pass --keep-volumes to preserve data.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

remove_volumes=true
if [[ "${1:-}" == "--keep-volumes" ]]; then
  remove_volumes=false
  shift
fi

down_args=()
if $remove_volumes; then
  down_args+=("--volumes")
fi

# Reverse order so dependents stop before their dependencies.
services=(
  # "VectorDBs"
  # "Observability/Jaeger"
  # "Observability/Grafana"
  # "Observability/Prometheus"
  "Airflow"
  "Postgres"
)

for svc in "${services[@]}"; do
  compose="$DIR/$svc/docker-compose.yml"
  if [[ -f "$compose" ]]; then
    echo "==> Stopping $svc"
    docker compose -f "$compose" down "${down_args[@]}"
  fi
done
