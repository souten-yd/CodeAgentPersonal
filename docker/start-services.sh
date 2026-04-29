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

has_sbv2_weight_file() {
  local dir="$1"
  local weight
  for weight in     "$dir"/*.safetensors     "$dir"/*.pth     "$dir"/*.pt     "$dir"/*.onnx
  do
    if [ -f "$weight" ]; then
      echo "$weight"
      return 0
    fi
  done
  return 1
}

validate_sbv2_model_dir() {
  local dir="$1"
  local name="$2"

  if [ ! -d "$dir" ]; then
    echo "[Style-Bert-VITS2] ${name} missing directory: $dir" >&2
    return 1
  fi
  if [ ! -f "$dir/config.json" ]; then
    echo "[Style-Bert-VITS2] ${name} missing config.json: $dir/config.json" >&2
    return 1
  fi
  if [ ! -f "$dir/style_vectors.npy" ]; then
    echo "[Style-Bert-VITS2] ${name} missing style_vectors.npy: $dir/style_vectors.npy" >&2
    return 1
  fi
  local weight_file
  weight_file="$(has_sbv2_weight_file "$dir" || true)"
  if [ -z "$weight_file" ]; then
    echo "[Style-Bert-VITS2] ${name} missing weight file in: $dir" >&2
    return 1
  fi
  echo "[Style-Bert-VITS2] ${name} detected weight file: ${weight_file}"
  return 0
}

backup_invalid_sbv2_path() {
  local path="$1"
  local ts
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  local backup="${path}.broken-${ts}-$$"
  local suffix=0
  while [ -e "$backup" ] || [ -L "$backup" ]; do
    suffix=$((suffix + 1))
    backup="${path}.broken-${ts}-$$-${suffix}"
  done
  echo "[Style-Bert-VITS2] moving invalid koharune-ami path to: ${backup}" >&2
  mv "$path" "$backup"
}

link_bundled_sbv2_model() {
  echo "[Style-Bert-VITS2] linking bundled koharune-ami into workspace"
  ln -s "${SBV2_BUNDLED_MODEL_PATH}" "${SBV2_WORKSPACE_MODEL_PATH}"
}

if [ ! -x /opt/style-bert-vits2-venv/bin/python ]; then
  echo "[Style-Bert-VITS2] FATAL: missing venv python: /opt/style-bert-vits2-venv/bin/python" >&2
  exit 1
fi
if [ ! -d /app/Style-Bert-VITS2 ]; then
  echo "[Style-Bert-VITS2] FATAL: missing repo dir: /app/Style-Bert-VITS2" >&2
  exit 1
fi
if [ ! -f /app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm/pytorch_model.bin ]; then
  echo "[Style-Bert-VITS2] FATAL: missing Japanese BERT pytorch_model.bin" >&2
  exit 1
fi
if [ ! -f /app/Style-Bert-VITS2/bert/deberta-v2-large-japanese-char-wwm-onnx/model_fp16.onnx ]; then
  echo "[Style-Bert-VITS2] FATAL: missing Japanese BERT ONNX model_fp16.onnx" >&2
  exit 1
fi

mkdir -p "${SBV2_WORKSPACE_MODELS_DIR}"

if ! validate_sbv2_model_dir "${SBV2_BUNDLED_MODEL_PATH}" "bundled koharune-ami"; then
  echo "[Style-Bert-VITS2] FATAL: bundled koharune-ami is invalid. Docker image is incomplete." >&2
  exit 1
fi

if [ -L "${SBV2_WORKSPACE_MODEL_PATH}" ]; then
  LINK_TARGET="$(readlink "${SBV2_WORKSPACE_MODEL_PATH}" || true)"
  if validate_sbv2_model_dir "${SBV2_WORKSPACE_MODEL_PATH}" "workspace koharune-ami symlink"; then
    echo "[Style-Bert-VITS2] workspace koharune-ami symlink is valid: ${SBV2_WORKSPACE_MODEL_PATH} -> ${LINK_TARGET}"
  else
    echo "[Style-Bert-VITS2] workspace koharune-ami symlink is invalid or broken: ${SBV2_WORKSPACE_MODEL_PATH} -> ${LINK_TARGET}" >&2
    backup_invalid_sbv2_path "${SBV2_WORKSPACE_MODEL_PATH}"
    link_bundled_sbv2_model
  fi
elif [ -e "${SBV2_WORKSPACE_MODEL_PATH}" ]; then
  if validate_sbv2_model_dir "${SBV2_WORKSPACE_MODEL_PATH}" "workspace koharune-ami"; then
    echo "[Style-Bert-VITS2] workspace koharune-ami real path is valid; keeping it: ${SBV2_WORKSPACE_MODEL_PATH}"
  else
    echo "[Style-Bert-VITS2] workspace koharune-ami exists but is invalid; replacing with bundled symlink" >&2
    backup_invalid_sbv2_path "${SBV2_WORKSPACE_MODEL_PATH}"
    link_bundled_sbv2_model
  fi
else
  link_bundled_sbv2_model
fi

if ! validate_sbv2_model_dir "${SBV2_WORKSPACE_MODEL_PATH}" "final workspace koharune-ami"; then
  echo "[Style-Bert-VITS2] FATAL: final workspace koharune-ami is invalid after repair." >&2
  exit 1
fi

FINAL_LINK_TARGET="$(readlink "${SBV2_WORKSPACE_MODEL_PATH}" 2>/dev/null || echo "(not a symlink)")"
echo "[Style-Bert-VITS2] final workspace model path: ${SBV2_WORKSPACE_MODEL_PATH}"
echo "[Style-Bert-VITS2] final workspace model readlink: ${FINAL_LINK_TARGET}"
echo "[Style-Bert-VITS2] bundled model path: ${SBV2_BUNDLED_MODEL_PATH}"
echo "[Style-Bert-VITS2] validate success: workspace koharune-ami is ready"

if [ "${AUTO_START_SEARXNG}" = "true" ]; then
  bash /app/scripts/start_searxng.sh || echo "[SearXNG][WARN] start_searxng.sh failed; continuing FastAPI startup."
fi

exec python scripts/start_codeagent.py --host "$HOST" --port "$PORT" --primary-port "$PRIMARY_PORT"
