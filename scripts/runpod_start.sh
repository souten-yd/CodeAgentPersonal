#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PORT="${PORT:-5000}"
HOST="${HOST:-0.0.0.0}"
PRIMARY_PORT="${PRIMARY_PORT:-8080}"
WORKSPACE_ROOT="${RUNPOD_WORKSPACE_ROOT:-/workspace}"
IS_RUNPOD_RUNTIME="false"
# NOTE: Keep this aligned with scripts/start_codeagent.py::detect_runpod()
if [[ -n "${RUNPOD_POD_ID:-}" || -n "${RUNPOD_API_KEY:-}" ]]; then
  IS_RUNPOD_RUNTIME="true"
fi

echo "[Runpod] Booting CodeAgent from ${ROOT_DIR}"
echo "[Runpod] host=${HOST} port=${PORT} primary_port=${PRIMARY_PORT} workspace_root=${WORKSPACE_ROOT}"
echo "[Runpod] runtime_is_runpod=${IS_RUNPOD_RUNTIME}"

# Runpod標準値（未設定時のみ適用。明示指定は尊重）
export AUTO_START_SEARXNG="${AUTO_START_SEARXNG:-true}"
export DEFAULT_LLM_CTX_SIZE="${DEFAULT_LLM_CTX_SIZE:-16384}"
export LLAMA_CTX_SIZE="${LLAMA_CTX_SIZE:-${DEFAULT_LLM_CTX_SIZE}}"
export NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS="${NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS:-${DEFAULT_LLM_CTX_SIZE}}"
export NEXUS_WEB_SEARCH_PROVIDER="${NEXUS_WEB_SEARCH_PROVIDER:-searxng}"
export NEXUS_SEARXNG_URL="${NEXUS_SEARXNG_URL:-http://127.0.0.1:8088}"
export NEXUS_SEARCH_FREE_ONLY="${NEXUS_SEARCH_FREE_ONLY:-true}"
export NEXUS_SEARCH_PAID_PROVIDERS_ENABLED="${NEXUS_SEARCH_PAID_PROVIDERS_ENABLED:-false}"
export SEARXNG_PORT="${SEARXNG_PORT:-8088}"
export SEARXNG_BIND_ADDRESS="${SEARXNG_BIND_ADDRESS:-127.0.0.1}"
echo "[Runpod] AUTO_START_SEARXNG=${AUTO_START_SEARXNG}"
echo "[Runpod] DEFAULT_LLM_CTX_SIZE=${DEFAULT_LLM_CTX_SIZE} LLAMA_CTX_SIZE=${LLAMA_CTX_SIZE}"
echo "[Runpod] NEXUS_WEB_SEARCH_PROVIDER=${NEXUS_WEB_SEARCH_PROVIDER}"
echo "[Runpod] NEXUS_SEARXNG_URL=${NEXUS_SEARXNG_URL}"
echo "[Runpod] NEXUS_SEARCH_FREE_ONLY=${NEXUS_SEARCH_FREE_ONLY}"
echo "[Runpod] NEXUS_SEARCH_PAID_PROVIDERS_ENABLED=${NEXUS_SEARCH_PAID_PROVIDERS_ENABLED}"
echo "[Runpod] SEARXNG_PORT=${SEARXNG_PORT}"
echo "[Runpod] SEARXNG_BIND_ADDRESS=${SEARXNG_BIND_ADDRESS}"

AUTO_INSTALL_DOCKER="${RUNPOD_AUTO_INSTALL_DOCKER:-true}"
if [[ "${AUTO_INSTALL_DOCKER}" == "true" ]]; then
  if [[ "${IS_RUNPOD_RUNTIME}" == "true" ]]; then
    echo "[Runpod] Skipping docker.io auto-install on Runpod (managed Docker daemon; local Docker-in-Docker unsupported)."
  elif command -v docker >/dev/null 2>&1; then
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

SEARXNG_AUTOSTART_STATUS="${RUNPOD_SEARXNG_AUTOSTART_STATUS:-not_requested}"
SEARXNG_AUTOSTART_HINT="${RUNPOD_SEARXNG_AUTOSTART_HINT:-}"

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


# Install Qwen3-TTS runtime dependencies if missing (optional)
"${PYTHON_BIN}" -c "import qwen_tts, transformers, torch, torchaudio, soundfile" 2>/dev/null || {
  echo "[Runpod] Installing Qwen3-TTS dependencies (cu128 torch + qwen-tts)..."
  "${PYTHON_BIN}" -m pip install --upgrade-strategy only-if-needed \
    --index-url https://download.pytorch.org/whl/cu128 \
    -r requirements-tts.txt \
    && "${PYTHON_BIN}" -m pip install --upgrade-strategy only-if-needed -r requirements-tts-qwen.txt \
    && "${PYTHON_BIN}" -m pip check \
    && "${PYTHON_BIN}" -c "import qwen_tts, transformers, torch, torchaudio, soundfile" >/dev/null 2>&1 \
    || echo "[Runpod][WARN] qwen-tts/torch dependency installation failed. Qwen3 TTS will be disabled."
}
# Re-pin core framework versions in case optional deps caused downgrades
"${PYTHON_BIN}" -m pip install --upgrade "pydantic>=2.6" "fastapi>=0.110" 2>/dev/null || true

# Runpod専用デフォルト: Runpod起動スクリプトでは SearXNG 自動起動を既定で有効化する。
AUTO_START_SEARXNG="${AUTO_START_SEARXNG:-${RUNPOD_AUTO_START_SEARXNG:-true}}"
if [[ "${AUTO_START_SEARXNG}" == "true" ]]; then
  echo "[Runpod] SearXNG auto-start enabled."
  searxng_status_file="$(mktemp)"
  RUNPOD_SEARXNG_STATUS_OUTPUT_FILE="${searxng_status_file}" bash scripts/start_searxng.sh || true
  if [[ -s "${searxng_status_file}" ]]; then
    # shellcheck disable=SC1090
    source "${searxng_status_file}"
    SEARXNG_AUTOSTART_STATUS="${RUNPOD_SEARXNG_AUTOSTART_STATUS:-failed_unknown}"
    SEARXNG_AUTOSTART_HINT="${RUNPOD_SEARXNG_AUTOSTART_HINT:-SearXNG status unavailable. Check startup logs.}"
  else
    SEARXNG_AUTOSTART_STATUS="failed_status_unavailable"
    SEARXNG_AUTOSTART_HINT="SearXNG status file was not generated. Check startup logs."
  fi
  rm -f "${searxng_status_file}" || true
  if [[ "${SEARXNG_AUTOSTART_STATUS}" == failed_* ]]; then
    echo "[Runpod][SearXNG][WARN] ${SEARXNG_AUTOSTART_HINT}"
  fi
else
  echo "[Runpod] SearXNG auto-start disabled (RUNPOD_AUTO_START_SEARXNG=${AUTO_START_SEARXNG})."
  SEARXNG_AUTOSTART_STATUS="not_requested"
  SEARXNG_AUTOSTART_HINT="RUNPOD_AUTO_START_SEARXNG が true ではないため起動していません。"
fi


STYLE_BERT_BASE_DIR="${CODEAGENT_STYLE_BERT_VITS2_BASE_DIR:-${WORKSPACE_ROOT}/ca_data/tts/style_bert_vits2}"
STYLE_BERT_MODELS_DIR="${CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR:-${STYLE_BERT_BASE_DIR}/models}"
STYLE_BERT_SOURCE_MODELS_DIR="${RUNPOD_STYLE_BERT_VITS2_SOURCE_MODELS_DIR:-/app/Style-Bert-VITS2/model_assets}"
STYLE_BERT_REPO_DIR="${CODEAGENT_STYLE_BERT_VITS2_REPO_DIR:-${WORKSPACE_ROOT}/Style-Bert-VITS2}"
STYLE_BERT_REPO_FALLBACK="${RUNPOD_STYLE_BERT_VITS2_SOURCE_REPO_DIR:-/app/Style-Bert-VITS2}"
STYLE_BERT_VENV_FALLBACK="${RUNPOD_STYLE_BERT_VITS2_SOURCE_VENV_DIR:-/app/Style-Bert-VITS2/.venv}"
STYLE_BERT_BOOTSTRAP_VENV_DIR="${RUNPOD_STYLE_BERT_VITS2_BOOTSTRAP_VENV:-${WORKSPACE_ROOT}/.venvs/style-bert-vits2}"

mkdir -p "${STYLE_BERT_MODELS_DIR}"
mkdir -p "$(dirname "${STYLE_BERT_REPO_DIR}")"

if [[ ! -d "${STYLE_BERT_REPO_DIR}" && -d "${STYLE_BERT_REPO_FALLBACK}" ]]; then
  echo "[Runpod][SBV2] Workspace repo missing. Copying ${STYLE_BERT_REPO_FALLBACK} -> ${STYLE_BERT_REPO_DIR}"
  cp -a "${STYLE_BERT_REPO_FALLBACK}" "${STYLE_BERT_REPO_DIR}"
fi

if [[ -n "${CODEAGENT_STYLE_BERT_VITS2_VENV_DIR:-}" ]]; then
  STYLE_BERT_VENV_DIR="${CODEAGENT_STYLE_BERT_VITS2_VENV_DIR}"
elif [[ -d "${STYLE_BERT_REPO_DIR}/.venv" ]]; then
  STYLE_BERT_VENV_DIR="${STYLE_BERT_REPO_DIR}/.venv"
elif [[ -d "${STYLE_BERT_VENV_FALLBACK}" ]]; then
  # 既存venvはコピーせずそのまま利用（絶対パス混入・破損回避）
  STYLE_BERT_VENV_DIR="${STYLE_BERT_VENV_FALLBACK}"
else
  mkdir -p "${STYLE_BERT_BOOTSTRAP_VENV_DIR}"
  echo "[Runpod][SBV2] venv not found. Creating bootstrap venv at ${STYLE_BERT_BOOTSTRAP_VENV_DIR}"
  "${BOOTSTRAP_PYTHON}" -m venv "${STYLE_BERT_BOOTSTRAP_VENV_DIR}" || true
  STYLE_BERT_VENV_DIR="${STYLE_BERT_BOOTSTRAP_VENV_DIR}"
fi

if [[ -x "${STYLE_BERT_VENV_DIR}/bin/python" ]]; then
  echo "[Runpod][SBV2] runtime python detected: ${STYLE_BERT_VENV_DIR}/bin/python"
else
  echo "[Runpod][SBV2][WARN] runtime python missing under ${STYLE_BERT_VENV_DIR}"
fi

export CODEAGENT_STYLE_BERT_VITS2_BASE_DIR="${STYLE_BERT_BASE_DIR}"
export CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR="${STYLE_BERT_MODELS_DIR}"
export CODEAGENT_STYLE_BERT_VITS2_REPO_DIR="${STYLE_BERT_REPO_DIR}"
export CODEAGENT_STYLE_BERT_VITS2_VENV_DIR="${STYLE_BERT_VENV_DIR}"

if [[ -d "${STYLE_BERT_SOURCE_MODELS_DIR}" ]]; then
  if [[ -z "$(find "${STYLE_BERT_MODELS_DIR}" -mindepth 1 -maxdepth 1 2>/dev/null)" ]]; then
    echo "[Runpod] Copying Style-Bert-VITS2 models to workspace: ${STYLE_BERT_SOURCE_MODELS_DIR} -> ${STYLE_BERT_MODELS_DIR}"
    cp -a "${STYLE_BERT_SOURCE_MODELS_DIR}/." "${STYLE_BERT_MODELS_DIR}/"
  else
    echo "[Runpod] Style-Bert-VITS2 models dir already has content. Skip copy: ${STYLE_BERT_MODELS_DIR}"
  fi
else
  echo "[Runpod] Style-Bert-VITS2 source models dir not found. Skip copy: ${STYLE_BERT_SOURCE_MODELS_DIR}"
fi

echo "[Runpod][SBV2] base_dir=${CODEAGENT_STYLE_BERT_VITS2_BASE_DIR}"
echo "[Runpod][SBV2] repo_dir=${CODEAGENT_STYLE_BERT_VITS2_REPO_DIR} (fallback=${STYLE_BERT_REPO_FALLBACK})"
echo "[Runpod][SBV2] venv_dir=${CODEAGENT_STYLE_BERT_VITS2_VENV_DIR} (fallback=${STYLE_BERT_VENV_FALLBACK}; existing venv is not copied)"
echo "[Runpod][SBV2] models_dir=${CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR} (source=${STYLE_BERT_SOURCE_MODELS_DIR})"
if [[ -d "${CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR}" ]]; then
  echo "[Runpod][SBV2] models listing:"
  find "${CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR}" -mindepth 1 -maxdepth 2 -type f \( -name 'config.json' -o -name 'style_vectors.npy' -o -name '*.safetensors' -o -name '*.pth' -o -name '*.pt' -o -name '*.onnx' \) | sed 's/^/[Runpod][SBV2]   /' || true
fi
echo "[Runpod] FastAPI will start on port ${PORT} (override with PORT env)."

export RUNPOD_SEARXNG_AUTOSTART_STATUS="${SEARXNG_AUTOSTART_STATUS}"
export RUNPOD_SEARXNG_AUTOSTART_HINT="${SEARXNG_AUTOSTART_HINT}"

exec "${PYTHON_BIN}" scripts/start_codeagent.py \
  --host "${HOST}" \
  --port "${PORT}" \
  --primary-port "${PRIMARY_PORT}"
