#!/usr/bin/env bash
set -euo pipefail

cd /app

HOST="${CODEAGENT_HOST:-0.0.0.0}"
PORT="${CODEAGENT_PORT:-8000}"
PRIMARY_PORT="${LLAMA_PORT:-8080}"

if command -v sox >/dev/null 2>&1; then
  echo "[Qwen3-TTS] sox binary: $(command -v sox)"
else
  echo "[Qwen3-TTS] warning: SoX command is missing (sox not found in PATH). Qwen3-TTS will continue with limited/slower audio paths."
fi

exec python scripts/start_codeagent.py --host "$HOST" --port "$PORT" --primary-port "$PRIMARY_PORT"
