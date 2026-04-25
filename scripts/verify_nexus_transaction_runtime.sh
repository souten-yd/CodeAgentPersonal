#!/usr/bin/env bash
set -euo pipefail

HOST="${VERIFY_HOST:-127.0.0.1}"
PORT="${VERIFY_PORT:-8899}"
STARTUP_WAIT="${VERIFY_STARTUP_WAIT:-3}"

log() {
  echo "[verify_nexus_transaction] $*"
}

run_import_check() {
  python - <<'PY'
from app.nexus.db import transaction
print(f"transaction import OK: {callable(transaction)}")
PY
}

start_server() {
  local log_file="$1"
  uvicorn main:app --host "$HOST" --port "$PORT" >"$log_file" 2>&1 &
  STARTED_PID=$!
}

stop_server() {
  local pid="$1"
  kill "$pid" || true
  wait "$pid" || true
}

verify_container_file() {
  if [[ -f /app/app/nexus/db.py ]]; then
    log "Detected /app/app/nexus/db.py; comparing with repository copy."
    sha256sum app/nexus/db.py /app/app/nexus/db.py
    if diff -u app/nexus/db.py /app/app/nexus/db.py >/tmp/nexus_db_diff.txt; then
      log "Container file matches repository file."
    else
      log "Container file differs from repository file (possible bind mount / image mismatch)."
      sed -n '1,80p' /tmp/nexus_db_diff.txt
    fi
  else
    log "/app/app/nexus/db.py not present in this environment (non-Docker path or different mount)."
  fi
}

clear_pycache() {
  local pycache_dirs
  pycache_dirs="$(find app -type d -name '__pycache__' -print || true)"

  if [[ -n "$pycache_dirs" ]]; then
    log "Removing __pycache__ directories:"
    echo "$pycache_dirs"
    find app -type d -name '__pycache__' -prune -exec rm -rf {} +
  else
    log "No __pycache__ directories found under app/."
  fi
}

assert_log_clean() {
  local log_file="$1"
  if rg -n "ImportError|cannot import name 'transaction'|Traceback" "$log_file"; then
    log "Unexpected import error pattern found in startup log."
    return 1
  fi
  log "No transaction-related import error pattern found in startup log."
}

main() {
  log "Step 1/5: Baseline import check in a fresh Python process."
  run_import_check

  log "Step 2/5: Restarting server process, then re-checking import."
  local log1 log2 pid1 pid2
  log1="$(mktemp)"
  log2="$(mktemp)"
  start_server "$log1"
  pid1="$STARTED_PID"
  sleep "$STARTUP_WAIT"
  stop_server "$pid1"

  start_server "$log2"
  pid2="$STARTED_PID"
  sleep "$STARTUP_WAIT"
  run_import_check
  stop_server "$pid2"

  log "Startup logs after restart:"
  sed -n '1,40p' "$log2"

  log "Step 3/5: Docker/Runpod runtime path consistency check."
  verify_container_file

  log "Step 4/5: Clearing __pycache__ and restarting server."
  clear_pycache

  local log3 pid3
  log3="$(mktemp)"
  start_server "$log3"
  pid3="$STARTED_PID"
  sleep "$STARTUP_WAIT"
  run_import_check
  stop_server "$pid3"

  log "Step 5/5: Verifying startup log does not contain transaction import failures."
  sed -n '1,60p' "$log3"
  assert_log_clean "$log3"

  log "Verification complete."
}

main "$@"
