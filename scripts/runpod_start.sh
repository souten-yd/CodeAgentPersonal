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
# Prefer official expanded_assets wheels, then fallback to PyPI.
"${PYTHON_BIN}" -c "import voicevox_core" 2>/dev/null || {
  echo "[Runpod] Installing voicevox_core for VOICEVOX TTS..."
  "${PYTHON_BIN}" -m pip install voicevox_core --no-index \
    --find-links "https://github.com/VOICEVOX/voicevox_core/releases/expanded_assets/0.15.0/" \
    || "${PYTHON_BIN}" -m pip install "voicevox_core>=0.15,<0.16" \
    || echo "[Runpod][WARN] voicevox_core installation failed. VOICEVOX TTS will be disabled."
}
if "${PYTHON_BIN}" -c "import voicevox_core,sys; print(f'voicevox_core OK (python={sys.executable})')" >/tmp/voicevox_import_check.log 2>&1; then
  cat /tmp/voicevox_import_check.log
else
  echo "[Runpod][WARN] voicevox_core import check failed:"
  cat /tmp/voicevox_import_check.log || true
  "${PYTHON_BIN}" -m pip show voicevox_core || true
fi
# Prepare Open JTalk dictionary automatically (for VOICEVOX).
JTALK_DIR="/workspace/ca_data/tts/open_jtalk_dic_utf_8-1.11"
if [[ ! -d "${JTALK_DIR}" || -z "$(ls -A "${JTALK_DIR}" 2>/dev/null || true)" ]]; then
  echo "[Runpod] Open JTalk dictionary not found. Trying automatic setup..."
  mkdir -p /workspace/ca_data/tts
  TMP_TGZ="/tmp/open_jtalk_dic_utf_8-1.11.tar.gz"
  JTALK_URLS=(
    "https://downloads.sourceforge.net/project/open-jtalk/Dictionary/open_jtalk_dic-1.11/open_jtalk_dic_utf_8-1.11.tar.gz"
    "https://downloads.sourceforge.net/project/open-jtalk/Dictionary/open_jtalk_dic_utf_8-1.11/open_jtalk_dic_utf_8-1.11.tar.gz"
  )
  DL_OK=0
  for url in "${JTALK_URLS[@]}"; do
    if curl -fL --retry 3 --retry-delay 2 "${url}" -o "${TMP_TGZ}"; then
      DL_OK=1
      break
    fi
  done
  if [[ "${DL_OK}" -eq 1 ]]; then
    EXTRACT_DIR="/tmp/openjtalk_extract"
    rm -rf "${EXTRACT_DIR}"
    mkdir -p "${EXTRACT_DIR}"
    if tar -xzf "${TMP_TGZ}" -C "${EXTRACT_DIR}"; then
      FOUND_DIR="$(find "${EXTRACT_DIR}" -type d -name open_jtalk_dic_utf_8-1.11 | head -n1 || true)"
      if [[ -n "${FOUND_DIR}" ]]; then
        rm -rf "${JTALK_DIR}"
        mv "${FOUND_DIR}" "${JTALK_DIR}"
        echo "[Runpod] Open JTalk dictionary prepared at ${JTALK_DIR}"
      fi
    fi
  fi
fi
if [[ ! -d "${JTALK_DIR}" || -z "$(ls -A "${JTALK_DIR}" 2>/dev/null || true)" ]]; then
  echo "[Runpod][WARN] Open JTalk dictionary setup failed. Please place open_jtalk_dic_utf_8-1.11 under /workspace/ca_data/tts."
fi
# Re-pin core framework versions in case optional deps caused downgrades
"${PYTHON_BIN}" -m pip install --upgrade "pydantic>=2.6" "fastapi>=0.110" 2>/dev/null || true

exec "${PYTHON_BIN}" scripts/start_codeagent.py \
  --host "${HOST}" \
  --port "${PORT}" \
  --primary-port "${PRIMARY_PORT}"
