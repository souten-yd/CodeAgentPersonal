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

echo "[Runpod] llama-server can be auto-setup at launch with a CUDA source build (RUNPOD_AUTO_SETUP_LLAMA=true)."
echo "[Runpod] You can also provide an explicit binary path with LLAMA_SERVER_PATH."

BOOTSTRAP_VENV="${RUNPOD_BOOTSTRAP_VENV:-/workspace/.venvs/codeagent-bootstrap}"
BOOTSTRAP_PYTHON="${RUNPOD_BOOTSTRAP_PYTHON:-}"
if [[ -z "${BOOTSTRAP_PYTHON}" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    BOOTSTRAP_PYTHON="python3.11"
  elif command -v python3 >/dev/null 2>&1; then
    BOOTSTRAP_PYTHON="python3"
  else
    echo "[Runpod][ERROR] python3.11/python3 was not found." >&2
    exit 1
  fi
fi

echo "[Runpod] Bootstrap Python: ${BOOTSTRAP_PYTHON}"

PYTHON_BIN="${BOOTSTRAP_VENV}/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[Runpod] Creating bootstrap venv at ${BOOTSTRAP_VENV}"
  "${BOOTSTRAP_PYTHON}" -m venv "${BOOTSTRAP_VENV}"
fi

"${PYTHON_BIN}" scripts/check_environment.py || {
  echo "[Runpod] Installing Python dependencies into bootstrap venv..."
  "${PYTHON_BIN}" -m pip install --upgrade pip
  "${PYTHON_BIN}" -m pip install -r requirements.txt
}

# Install voicevox_core if not present (optional: VOICEVOX TTS)
# Install explicit wheel URL (CUDA -> CPU fallback).
# Avoid `--find-links ... voicevox_core` to prevent cpu/cuda dual-candidate conflicts.
"${PYTHON_BIN}" -c "import voicevox_core" 2>/dev/null || {
  echo "[Runpod] Installing voicevox_core for VOICEVOX TTS..."
  VV_CUDA_URL="https://github.com/VOICEVOX/voicevox_core/releases/download/0.15.0/voicevox_core-0.15.0%2Bcuda-cp38-abi3-linux_x86_64.whl"
  VV_CPU_URL="https://github.com/VOICEVOX/voicevox_core/releases/download/0.15.0/voicevox_core-0.15.0%2Bcpu-cp38-abi3-linux_x86_64.whl"
  VV_ORDER=()
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    VV_ORDER=("${VV_CUDA_URL}" "${VV_CPU_URL}")
  else
    # AMD/Intel/no-GPU 環境はCPU wheelを優先
    VV_ORDER=("${VV_CPU_URL}" "${VV_CUDA_URL}")
  fi
  VV_OK=0
  for vv_url in "${VV_ORDER[@]}"; do
    "${PYTHON_BIN}" -m pip uninstall -y voicevox_core >/dev/null 2>&1 || true
    if "${PYTHON_BIN}" -m pip install --no-deps "${vv_url}" \
      && "${PYTHON_BIN}" -c "import voicevox_core" >/dev/null 2>&1; then
      VV_OK=1
      break
    fi
  done
  if [[ "${VV_OK}" -ne 1 ]]; then
    echo "[Runpod][WARN] voicevox_core installation failed. VOICEVOX TTS will be disabled."
  fi
}
# Install torch (CUDA) + qwen-tts if not present (optional: Qwen3 TTS)
"${PYTHON_BIN}" -c "import qwen_tts" 2>/dev/null || {
  echo "[Runpod] Installing torch (CUDA 12.4) + qwen-tts for Qwen3 TTS..."
  "${PYTHON_BIN}" -m pip install torch torchaudio \
    --index-url https://download.pytorch.org/whl/cu124 \
    && "${PYTHON_BIN}" -m pip install qwen-tts soundfile \
    || echo "[Runpod][WARN] qwen-tts installation failed. Qwen3 TTS will be disabled."
}
# Re-pin core framework versions in case optional deps caused downgrades
"${PYTHON_BIN}" -m pip install --upgrade "pydantic>=2.6" "fastapi>=0.110" 2>/dev/null || true

exec "${PYTHON_BIN}" scripts/start_codeagent.py \
  --host "${HOST}" \
  --port "${PORT}" \
  --primary-port "${PRIMARY_PORT}"
