#!/usr/bin/env bash
# `npm run services:stop` — terminate any DataMgmt / RAGMgmt processes started
# via start-services.sh. Idempotent.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/_common.sh"

PID_DIR="${PID_DIR:-/tmp/rhc-rag-pids}"

stop_one() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"
  if [[ ! -f "$pid_file" ]]; then
    echo "[$name] no pid file"
    return 0
  fi
  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "[$name] stopping pid $pid"
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  else
    echo "[$name] pid $pid not running"
  fi
  rm -f "$pid_file"
}

stop_one datamgmt
stop_one ragmgmt
