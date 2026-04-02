#!/usr/bin/env bash
# setup_longcat_tts.sh
# Creates a dedicated Python venv for LongCat-AudioDiT TTS.
#
# LongCat requires transformers>=5.3.0, which is INCOMPATIBLE with Qwen3-TTS
# (transformers==4.57.3). This script isolates them in separate environments.
#
# Usage:
#   # Runpod (default):
#   bash scripts/setup_longcat_tts.sh
#
#   # Local PC (creates .venv-longcat in project root):
#   bash scripts/setup_longcat_tts.sh --local
#
#   # Custom venv path:
#   LONGCAT_TTS_VENV=/path/to/venv bash scripts/setup_longcat_tts.sh
#
#   # CPU-only (no CUDA):
#   bash scripts/setup_longcat_tts.sh --cpu
#
# Environment variables:
#   LONGCAT_TTS_VENV    - venv path (overrides defaults)
#   LONGCAT_REPO_DIR    - where to clone/find the LongCat repo
#   LONGCAT_CUDA_VER    - PyTorch CUDA variant, e.g. "cu128" (default) or "cpu"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Parse flags
IS_LOCAL=false
IS_CPU=false
for arg in "$@"; do
  case "${arg}" in
    --local) IS_LOCAL=true ;;
    --cpu)   IS_CPU=true ;;
  esac
done

# CUDA variant
CUDA_VER="${LONGCAT_CUDA_VER:-cu128}"
if [[ "${IS_CPU}" == "true" ]]; then
  CUDA_VER="cpu"
fi

# Detect if running on Runpod
IS_RUNPOD=false
if [[ -n "${RUNPOD_POD_ID:-}" || -n "${RUNPOD_API_KEY:-}" ]]; then
  IS_RUNPOD=true
fi

# Venv path
if [[ -n "${LONGCAT_TTS_VENV:-}" ]]; then
  VENV_DIR="${LONGCAT_TTS_VENV}"
elif [[ "${IS_RUNPOD}" == "true" ]]; then
  VENV_DIR="/workspace/.venvs/longcat-tts"
elif [[ "${IS_LOCAL}" == "true" ]]; then
  VENV_DIR="${ROOT_DIR}/.venv-longcat"
else
  VENV_DIR="/workspace/.venvs/longcat-tts"
fi

# Repo directory
if [[ -n "${LONGCAT_REPO_DIR:-}" ]]; then
  REPO_DIR="${LONGCAT_REPO_DIR}"
elif [[ "${IS_RUNPOD}" == "true" || "${IS_LOCAL}" == "false" ]]; then
  REPO_DIR="/workspace/LongCat-AudioDiT"
else
  REPO_DIR="${ROOT_DIR}/ca_data/tts/longcattts/repo"
fi

echo "[LongCat-TTS] Setup starting"
echo "[LongCat-TTS] venv_dir=${VENV_DIR}"
echo "[LongCat-TTS] repo_dir=${REPO_DIR}"
echo "[LongCat-TTS] cuda_ver=${CUDA_VER}"
echo "[LongCat-TTS] is_runpod=${IS_RUNPOD} is_local=${IS_LOCAL}"

# ── Python binary ──────────────────────────────────────────────────────────────
PYTHON_BIN=""
for candidate in python3.11 python3.10 python3.12 python3; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    PYTHON_BIN="${candidate}"
    break
  fi
done
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "[LongCat-TTS][ERROR] No Python 3 found." >&2
  exit 1
fi
echo "[LongCat-TTS] Python: $(command -v ${PYTHON_BIN}) ($(${PYTHON_BIN} --version))"

# ── Create venv ────────────────────────────────────────────────────────────────
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "[LongCat-TTS] Creating venv at ${VENV_DIR}..."
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
else
  echo "[LongCat-TTS] Venv already exists at ${VENV_DIR}, skipping creation."
fi
PY="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"

# ── Upgrade pip ────────────────────────────────────────────────────────────────
"${PIP}" install --upgrade pip --quiet

# ── Install PyTorch ────────────────────────────────────────────────────────────
TORCH_ALREADY_OK=false
if "${PY}" -c "import torch; assert torch.__version__" >/dev/null 2>&1; then
  TORCH_ALREADY_OK=true
fi

if [[ "${TORCH_ALREADY_OK}" == "false" ]]; then
  if [[ "${CUDA_VER}" == "cpu" ]]; then
    echo "[LongCat-TTS] Installing PyTorch (CPU)..."
    "${PIP}" install torch torchaudio \
      --index-url https://download.pytorch.org/whl/cpu \
      --quiet
  else
    echo "[LongCat-TTS] Installing PyTorch (CUDA ${CUDA_VER})..."
    "${PIP}" install torch torchaudio \
      --index-url "https://download.pytorch.org/whl/${CUDA_VER}" \
      --quiet
  fi
else
  echo "[LongCat-TTS] PyTorch already installed, skipping."
fi

# ── Clone LongCat repo ─────────────────────────────────────────────────────────
LONGCAT_GITHUB="https://github.com/meituan-longcat/LongCat-AudioDiT.git"
if [[ ! -d "${REPO_DIR}" ]]; then
  echo "[LongCat-TTS] Cloning ${LONGCAT_GITHUB} -> ${REPO_DIR}..."
  mkdir -p "$(dirname "${REPO_DIR}")"
  git clone --depth 1 "${LONGCAT_GITHUB}" "${REPO_DIR}"
elif [[ ! -f "${REPO_DIR}/audiodit/__init__.py" ]]; then
  echo "[LongCat-TTS][WARN] Repo dir exists but seems incomplete: ${REPO_DIR}"
  echo "[LongCat-TTS] Re-cloning..."
  rm -rf "${REPO_DIR}"
  mkdir -p "$(dirname "${REPO_DIR}")"
  git clone --depth 1 "${LONGCAT_GITHUB}" "${REPO_DIR}"
else
  echo "[LongCat-TTS] Repo already present at ${REPO_DIR}"
fi

# ── Install LongCat package (audiodit + utils) ─────────────────────────────────
echo "[LongCat-TTS] Installing LongCat package from ${REPO_DIR}..."
if [[ -f "${REPO_DIR}/setup.py" || -f "${REPO_DIR}/pyproject.toml" ]]; then
  "${PIP}" install -e "${REPO_DIR}" --quiet
else
  # No setup.py: install only the requirements; rely on PYTHONPATH/LONGCAT_REPO_DIR
  echo "[LongCat-TTS][INFO] No setup.py/pyproject.toml found. Installing requirements only."
  "${PIP}" install -r "${ROOT_DIR}/requirements-tts-longcat.txt" --quiet
fi

# ── Install remaining dependencies ────────────────────────────────────────────
echo "[LongCat-TTS] Installing requirements-tts-longcat.txt..."
"${PIP}" install -r "${ROOT_DIR}/requirements-tts-longcat.txt" --quiet

# ── Verify ────────────────────────────────────────────────────────────────────
echo "[LongCat-TTS] Verifying installation..."
LONGCAT_REPO_DIR="${REPO_DIR}" "${PY}" - <<'VERIFY'
import sys, os
repo = os.environ.get("LONGCAT_REPO_DIR","")
if repo and repo not in sys.path:
    sys.path.insert(0, repo)
errors = []
for pkg in ["torch","torchaudio","transformers","soundfile","librosa","numpy","einops","safetensors"]:
    try:
        __import__(pkg)
    except ImportError as e:
        errors.append(f"{pkg}: {e}")
try:
    import audiodit
except ImportError as e:
    errors.append(f"audiodit: {e}")
try:
    from utils import normalize_text
except ImportError as e:
    errors.append(f"utils: {e}")
import transformers
print(f"  transformers={transformers.__version__}")
import torch
print(f"  torch={torch.__version__} cuda={torch.cuda.is_available()}")
if errors:
    print("ERRORS:", errors)
    sys.exit(1)
else:
    print("[LongCat-TTS] All imports OK.")
VERIFY

# Write marker file so main.py can detect the venv
MARKER_DIR="${VENV_DIR}"
cat > "${MARKER_DIR}/longcat_tts_info.json" <<JSON
{
  "venv_dir": "${VENV_DIR}",
  "repo_dir": "${REPO_DIR}",
  "cuda_ver": "${CUDA_VER}",
  "setup_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON

echo ""
echo "[LongCat-TTS] Setup complete."
echo "[LongCat-TTS] venv:      ${VENV_DIR}"
echo "[LongCat-TTS] repo:      ${REPO_DIR}"
echo "[LongCat-TTS] marker:    ${MARKER_DIR}/longcat_tts_info.json"
echo ""
echo "To use from CodeAgent, set in your environment:"
echo "  LONGCAT_TTS_VENV=${VENV_DIR}"
echo "  LONGCAT_REPO_DIR=${REPO_DIR}"
