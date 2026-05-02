#!/usr/bin/env bash
# `npm run services:start` — bootstrap venv, then start both DataMgmt-Service
# and RAGMgmt-Service in the background. PIDs land in /tmp; logs in /tmp too.
# Use `npm run services:stop` to terminate.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/_common.sh"
require_in_venv

PID_DIR="${PID_DIR:-/tmp/rhc-rag-pids}"
LOG_DIR="${LOG_DIR:-/tmp/rhc-rag-logs}"
mkdir -p "$PID_DIR" "$LOG_DIR"

start_one() {
  local name="$1" service_dir="$2" port="$3"
  local pid_file="$PID_DIR/$name.pid"
  local log_file="$LOG_DIR/$name.log"

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "[$name] already running (pid $(cat "$pid_file"))"
    return 0
  fi
  echo "[$name] starting on :$port (log: $log_file)"
  (
    cd "$service_dir"
    nohup "$VENV_UVICORN" main:app --host "${API_HOST:-0.0.0.0}" --port "$port" >"$log_file" 2>&1 &
    echo $! > "$pid_file"
  )
  sleep 1
  echo "[$name] pid $(cat "$pid_file")"
}

start_one datamgmt "$REPO_ROOT/middleware/DataMgmt-Service" "${DATAMGMT_PORT:-8001}"
start_one ragmgmt "$REPO_ROOT/middleware/RAGMgmt-Service" "${RAGMGMT_PORT:-8002}"
echo "Both services started. Use 'npm run services:stop' to terminate."
