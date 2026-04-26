#!/usr/bin/env bash
set -euo pipefail

cd /app

HOST="${CODEAGENT_HOST:-0.0.0.0}"
PORT="${CODEAGENT_PORT:-8000}"
PRIMARY_PORT="${LLAMA_PORT:-8080}"
AUTO_START_SEARXNG="${AUTO_START_SEARXNG:-false}"

if command -v sox >/dev/null 2>&1; then
  echo "[Qwen3-TTS] sox binary: $(command -v sox)"
else
  echo "[Qwen3-TTS] warning: SoX command is missing (sox not found in PATH). Qwen3-TTS will continue with limited/slower audio paths."
fi

echo "[Qwen3-TTS][runtime] checking torch import..."
if python - <<'PY'
import torch
print(f"[Qwen3-TTS][runtime] torch import OK: version={torch.__version__}, cuda={torch.version.cuda}")
PY
then
  :
else
  echo "[Qwen3-TTS][runtime] torch import FAILED" >&2
  exit 1
fi

echo "[Qwen3-TTS][runtime] checking flash_attn import..."
if python - <<'PY'
import flash_attn
print(f"[Qwen3-TTS][runtime] flash_attn import OK: module={flash_attn.__name__}")
PY
then
  :
else
  echo "[Qwen3-TTS][runtime] flash_attn import FAILED" >&2
  if [ "${REQUIRE_FLASH_ATTN:-0}" = "1" ]; then
    echo "[Qwen3-TTS][runtime] REQUIRE_FLASH_ATTN=1, exiting (fail-fast)." >&2
    exit 1
  fi
  echo "[Qwen3-TTS][runtime] REQUIRE_FLASH_ATTN!=1, continuing without flash_attn." >&2
fi

if [ "${AUTO_START_SEARXNG}" = "true" ]; then
  echo "[SearXNG] auto-start enabled from container entrypoint."
  bash /app/scripts/start_searxng.sh || echo "[SearXNG][WARN] start_searxng.sh failed; continuing FastAPI startup."
else
  echo "[SearXNG] auto-start disabled (AUTO_START_SEARXNG=${AUTO_START_SEARXNG})."
fi

exec python scripts/start_codeagent.py --host "$HOST" --port "$PORT" --primary-port "$PRIMARY_PORT"
