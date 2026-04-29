#!/usr/bin/env bash
set -euo pipefail

cd /app

HOST="${CODEAGENT_HOST:-0.0.0.0}"
PORT="${CODEAGENT_PORT:-8000}"
PRIMARY_PORT="${LLAMA_PORT:-8080}"
IS_RUNPOD_RUNTIME="false"
if [[ -n "${RUNPOD_POD_ID:-}" || -n "${RUNPOD_API_KEY:-}" ]]; then
  IS_RUNPOD_RUNTIME="true"
fi
if [[ "${IS_RUNPOD_RUNTIME}" == "true" ]]; then
  AUTO_START_SEARXNG="${AUTO_START_SEARXNG:-true}"
else
  AUTO_START_SEARXNG="${AUTO_START_SEARXNG:-false}"
fi

SBV2_WORKSPACE_MODELS_DIR="${CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR:-/workspace/ca_data/tts/style_bert_vits2/models}"
SBV2_BUNDLED_MODELS_DIR="/opt/style-bert-vits2-models"
SBV2_MODEL_NAME="koharune-ami"
SBV2_WORKSPACE_MODEL_PATH="${SBV2_WORKSPACE_MODELS_DIR}/${SBV2_MODEL_NAME}"
SBV2_BUNDLED_MODEL_PATH="${SBV2_BUNDLED_MODELS_DIR}/${SBV2_MODEL_NAME}"

mkdir -p "${SBV2_WORKSPACE_MODELS_DIR}"
if [ -L "${SBV2_WORKSPACE_MODEL_PATH}" ]; then
  LINK_TARGET="$(readlink "${SBV2_WORKSPACE_MODEL_PATH}" || true)"
  if [ "${LINK_TARGET}" != "${SBV2_BUNDLED_MODEL_PATH}" ]; then
    echo "[Style-Bert-VITS2] existing koharune-ami symlink points to ${LINK_TARGET}; keeping it"
  elif [ ! -d "${SBV2_BUNDLED_MODEL_PATH}" ]; then
    echo "[Style-Bert-VITS2] WARNING: bundled koharune-ami target is missing: ${SBV2_BUNDLED_MODEL_PATH}"
  else
    echo "[Style-Bert-VITS2] bundled koharune-ami symlink already exists"
  fi
elif [ -e "${SBV2_WORKSPACE_MODEL_PATH}" ]; then
  echo "[Style-Bert-VITS2] workspace koharune-ami already exists as real file/directory; keeping it: ${SBV2_WORKSPACE_MODEL_PATH}"
else
  if [ -d "${SBV2_BUNDLED_MODEL_PATH}" ]; then
    echo "[Style-Bert-VITS2] linking bundled koharune-ami into workspace"
    ln -s "${SBV2_BUNDLED_MODEL_PATH}" "${SBV2_WORKSPACE_MODEL_PATH}"
  else
    echo "[Style-Bert-VITS2] WARNING: bundled koharune-ami not found: ${SBV2_BUNDLED_MODEL_PATH}"
  fi
fi

if [ "${AUTO_START_SEARXNG}" = "true" ]; then
  bash /app/scripts/start_searxng.sh || echo "[SearXNG][WARN] start_searxng.sh failed; continuing FastAPI startup."
fi

exec python scripts/start_codeagent.py --host "$HOST" --port "$PORT" --primary-port "$PRIMARY_PORT"
