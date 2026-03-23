#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
PRIMARY_PORT="${PRIMARY_PORT:-8080}"

echo "[Runpod] Booting CodeAgent from ${ROOT_DIR}"
echo "[Runpod] host=${HOST} port=${PORT} primary_port=${PRIMARY_PORT}"

AUTO_INSTALL_DOCKER="${RUNPOD_AUTO_INSTALL_DOCKER:-true}"
if [[ "${AUTO_INSTALL_DOCKER}" == "true" ]]; then
  if command -v docker >/dev/null 2>&1; then
    echo "[Runpod] docker command already exists. Skipping docker.io install."
  elif command -v apt-get >/dev/null 2>&1; then
    echo "[Runpod] docker not found. Installing docker.io from Ubuntu/Debian repository..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends docker.io || {
      echo "[Runpod][WARN] docker.io install failed. Continue without Docker."
    }
    docker --version || true
  else
    echo "[Runpod][WARN] apt-get is unavailable. Cannot install docker.io automatically."
  fi
else
  echo "[Runpod] Skipping docker.io auto-install (RUNPOD_AUTO_INSTALL_DOCKER=${AUTO_INSTALL_DOCKER})."
fi

echo "[Runpod] llama-server can be auto-setup at launch (RUNPOD_AUTO_SETUP_LLAMA=true)."
echo "[Runpod] You can also provide an explicit binary path with LLAMA_SERVER_PATH."

BOOTSTRAP_VENV="${RUNPOD_BOOTSTRAP_VENV:-/workspace/.venvs/codeagent-bootstrap}"
PYTHON_BIN="${BOOTSTRAP_VENV}/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[Runpod] Creating bootstrap venv at ${BOOTSTRAP_VENV}"
  python3 -m venv "${BOOTSTRAP_VENV}"
fi

"${PYTHON_BIN}" scripts/check_environment.py || {
  echo "[Runpod] Installing Python dependencies into bootstrap venv..."
  "${PYTHON_BIN}" -m pip install --upgrade pip
  "${PYTHON_BIN}" -m pip install -r requirements.txt
}

exec "${PYTHON_BIN}" scripts/start_codeagent.py \
  --host "${HOST}" \
  --port "${PORT}" \
  --primary-port "${PRIMARY_PORT}"
