#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
PRIMARY_PORT="${PRIMARY_PORT:-8080}"

echo "[Runpod] Booting CodeAgent from ${ROOT_DIR}"
echo "[Runpod] host=${HOST} port=${PORT} primary_port=${PRIMARY_PORT}"

python scripts/check_environment.py || {
  echo "[Runpod] Installing Python dependencies from requirements.txt..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
}

exec python scripts/start_codeagent.py \
  --host "${HOST}" \
  --port "${PORT}" \
  --primary-port "${PRIMARY_PORT}"
