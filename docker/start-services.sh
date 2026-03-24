#!/usr/bin/env bash
set -euo pipefail

cd /app

HOST="${CODEAGENT_HOST:-0.0.0.0}"
PORT="${CODEAGENT_PORT:-8000}"
PRIMARY_PORT="${LLAMA_PORT:-8080}"

exec python scripts/start_codeagent.py --host "$HOST" --port "$PORT" --primary-port "$PRIMARY_PORT"
