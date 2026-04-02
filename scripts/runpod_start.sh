#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
PRIMARY_PORT="${PRIMARY_PORT:-8080}"
IS_RUNPOD_RUNTIME="false"
# NOTE: Keep this aligned with scripts/start_codeagent.py::detect_runpod()
if [[ -n "${RUNPOD_POD_ID:-}" || -n "${RUNPOD_API_KEY:-}" ]]; then
  IS_RUNPOD_RUNTIME="true"
fi

echo "[Runpod] Booting CodeAgent from ${ROOT_DIR}"
echo "[Runpod] host=${HOST} port=${PORT} primary_port=${PRIMARY_PORT}"
echo "[Runpod] runtime_is_runpod=${IS_RUNPOD_RUNTIME}"

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

VOICEVOX_AUTOSTART_STATUS="${RUNPOD_VOICEVOX_AUTOSTART_STATUS:-not_requested}"
VOICEVOX_AUTOSTART_HINT=""

runpod_voicevox_autostart() {
  local auto_start="${RUNPOD_AUTO_START_VOICEVOX:-false}"
  local vv_url="${VOICEVOX_URL:-http://127.0.0.1:50021}"
  local vv_container="${RUNPOD_VOICEVOX_CONTAINER_NAME:-voicevox_engine}"
  local vv_image="${RUNPOD_VOICEVOX_IMAGE:-voicevox/voicevox_engine:cpu-ubuntu20.04-latest}"
  local vv_host="${RUNPOD_VOICEVOX_BIND_HOST:-127.0.0.1}"
  local vv_port="${RUNPOD_VOICEVOX_PORT:-50021}"
  local max_wait="${RUNPOD_VOICEVOX_START_TIMEOUT_SEC:-120}"

  if [[ "${auto_start}" != "true" ]]; then
    echo "[Runpod] VOICEVOX auto-start disabled (RUNPOD_AUTO_START_VOICEVOX=${auto_start})."
    return 0
  fi

  echo "[Runpod] VOICEVOX auto-start enabled."
  echo "[Runpod] target_url=${vv_url} container=${vv_container} image=${vv_image} bind=${vv_host}:${vv_port}"

  if [[ "${IS_RUNPOD_RUNTIME}" == "true" ]]; then
    echo "[Runpod][VOICEVOX] Runpod runtime detected. Skipping local docker start and checking configured VOICEVOX_URL only."
    if [[ "${vv_url}" == "http://127.0.0.1:50021" || "${vv_url}" == "http://localhost:50021" ]]; then
      VOICEVOX_AUTOSTART_STATUS="failed_runpod_localhost_url"
      VOICEVOX_AUTOSTART_HINT="RunpodではPod内で独自Docker daemonを起動できないため、VOICEVOX_URLに外部/別PodのURLを指定してください。例: http://<pod-id>.runpod.internal:50021"
    else
      VOICEVOX_AUTOSTART_STATUS="probe_only"
      VOICEVOX_AUTOSTART_HINT="Runpod mode: docker起動は行わず、VOICEVOX_URLの疎通確認のみ実施します。"
    fi
  fi

  if [[ "${IS_RUNPOD_RUNTIME}" != "true" ]] && ! command -v docker >/dev/null 2>&1; then
    VOICEVOX_AUTOSTART_STATUS="failed_no_docker"
    VOICEVOX_AUTOSTART_HINT="Docker command not found. Set VOICEVOX_URL to an external engine or enable RUNPOD_AUTO_INSTALL_DOCKER=true."
    echo "[Runpod][VOICEVOX][ERROR] ${VOICEVOX_AUTOSTART_HINT}"
    return 0
  fi

  if [[ "${IS_RUNPOD_RUNTIME}" != "true" ]] && ! docker info >/dev/null 2>&1; then
    VOICEVOX_AUTOSTART_STATUS="failed_docker_daemon"
    VOICEVOX_AUTOSTART_HINT="Docker daemon is not running. Start Docker service or set VOICEVOX_URL to an existing engine."
    echo "[Runpod][VOICEVOX][ERROR] ${VOICEVOX_AUTOSTART_HINT}"
    return 0
  fi

  if [[ "${IS_RUNPOD_RUNTIME}" != "true" ]]; then
    # 既存コンテナがいれば再利用、なければ新規作成
    if docker ps -a --format '{{.Names}}' | grep -Fxq "${vv_container}"; then
      if ! docker start "${vv_container}" >/dev/null 2>&1; then
        VOICEVOX_AUTOSTART_STATUS="failed_container_start"
        VOICEVOX_AUTOSTART_HINT="Existing VOICEVOX container failed to start. Check: docker logs ${vv_container}"
        echo "[Runpod][VOICEVOX][ERROR] ${VOICEVOX_AUTOSTART_HINT}"
        return 0
      fi
      echo "[Runpod][VOICEVOX] Reused existing container: ${vv_container}"
    else
      if ! docker run -d --name "${vv_container}" -p "${vv_host}:${vv_port}:50021" "${vv_image}" >/dev/null; then
        VOICEVOX_AUTOSTART_STATUS="failed_container_run"
        VOICEVOX_AUTOSTART_HINT="docker run failed. Verify image tag/network and check: docker images | grep voicevox"
        echo "[Runpod][VOICEVOX][ERROR] ${VOICEVOX_AUTOSTART_HINT}"
        return 0
      fi
      echo "[Runpod][VOICEVOX] Started new container: ${vv_container}"
    fi
  fi

  # /version + /speakers をポーリングして、話者1件以上になるまで待機
  local elapsed=0
  local speakers_count=0
  local version_ok=0
  while (( elapsed < max_wait )); do
    version_ok=0
    speakers_count=0
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS --max-time 2 "${vv_url}/version" >/dev/null 2>&1; then
        version_ok=1
      fi
      if (( version_ok == 1 )); then
        speakers_count="$(curl -fsS --max-time 3 "${vv_url}/speakers" 2>/dev/null | "${PYTHON_BIN}" -c 'import json,sys; data=json.load(sys.stdin); print(sum(len(x.get("styles", [])) for x in data))' 2>/dev/null || echo 0)"
      fi
    else
      version_ok="$("${PYTHON_BIN}" - <<'PY'
import os,requests
url=os.environ.get("VV_URL","http://127.0.0.1:50021")
try:
    r=requests.get(f"{url}/version",timeout=2)
    print(1 if r.status_code==200 else 0)
except Exception:
    print(0)
PY
)"
      if [[ "${version_ok}" == "1" ]]; then
        speakers_count="$("${PYTHON_BIN}" - <<'PY'
import os,requests
url=os.environ.get("VV_URL","http://127.0.0.1:50021")
try:
    data=requests.get(f"{url}/speakers",timeout=3).json()
    print(sum(len(x.get("styles", [])) for x in data))
except Exception:
    print(0)
PY
)"
      fi
    fi

    if [[ "${version_ok}" == "1" ]] && [[ "${speakers_count}" =~ ^[0-9]+$ ]] && (( speakers_count > 0 )); then
      if [[ "${VOICEVOX_AUTOSTART_STATUS}" != "probe_only" ]]; then
        VOICEVOX_AUTOSTART_STATUS="ready"
      fi
      VOICEVOX_AUTOSTART_HINT="VOICEVOX HTTP is ready at ${vv_url} (${speakers_count} speakers)."
      echo "[Runpod][VOICEVOX] Ready: ${VOICEVOX_AUTOSTART_HINT}"
      return 0
    fi

    sleep 2
    elapsed=$((elapsed + 2))
  done

  VOICEVOX_AUTOSTART_STATUS="failed_timeout"
  VOICEVOX_AUTOSTART_HINT="Timed out waiting for VOICEVOX /version and /speakers. Check VOICEVOX_URL=${vv_url} and docker logs ${vv_container}."
  echo "[Runpod][VOICEVOX][ERROR] ${VOICEVOX_AUTOSTART_HINT}"
  echo "[Runpod][VOICEVOX][ERROR] Diagnostics:"
  if [[ "${IS_RUNPOD_RUNTIME}" == "true" ]]; then
    echo "  - Runpod mode: local docker start is disabled."
    echo "  - Set VOICEVOX_URL to reachable endpoint (e.g. another Pod/internal service)."
  else
    echo "  - docker ps (voicevox):"
    docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'voicevox|NAME' || true
    echo "  - recent logs (${vv_container}):"
    docker logs --tail 40 "${vv_container}" 2>/dev/null || true
  fi
  return 0
}

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

# Ensure VOICEVOX-related Python packages are removed and not reintroduced.
"${PYTHON_BIN}" -m pip uninstall -y voicevox-core voicevox-client pyopenjtalk >/dev/null 2>&1 || true

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

VV_URL="${VOICEVOX_URL:-http://127.0.0.1:50021}" runpod_voicevox_autostart
export RUNPOD_VOICEVOX_AUTOSTART_STATUS="${VOICEVOX_AUTOSTART_STATUS}"
export RUNPOD_VOICEVOX_AUTOSTART_HINT="${VOICEVOX_AUTOSTART_HINT}"

# ── LongCat-AudioDiT TTS (optional, separate venv) ────────────────────────────
# LongCat requires transformers>=5.3.0, incompatible with Qwen3-TTS (==4.57.3).
# It runs in /workspace/.venvs/longcat-tts to avoid conflicts.
# Set RUNPOD_AUTO_SETUP_LONGCAT=true to enable automatic setup at launch.
LONGCAT_VENV="${LONGCAT_TTS_VENV:-/workspace/.venvs/longcat-tts}"
LONGCAT_REPO="${LONGCAT_REPO_DIR:-/workspace/LongCat-AudioDiT}"
RUNPOD_AUTO_SETUP_LONGCAT="${RUNPOD_AUTO_SETUP_LONGCAT:-false}"

if [[ "${RUNPOD_AUTO_SETUP_LONGCAT}" == "true" ]]; then
  if [[ -x "${LONGCAT_VENV}/bin/python" ]]; then
    echo "[Runpod][LongCat-TTS] Venv already exists at ${LONGCAT_VENV}, skipping setup."
  else
    echo "[Runpod][LongCat-TTS] Auto-setup enabled. Running scripts/setup_longcat_tts.sh..."
    LONGCAT_TTS_VENV="${LONGCAT_VENV}" LONGCAT_REPO_DIR="${LONGCAT_REPO}" \
      bash "${ROOT_DIR}/scripts/setup_longcat_tts.sh" \
      || echo "[Runpod][LongCat-TTS][WARN] setup_longcat_tts.sh failed. LongCat TTS will be disabled."
  fi
else
  echo "[Runpod][LongCat-TTS] Auto-setup disabled (RUNPOD_AUTO_SETUP_LONGCAT=${RUNPOD_AUTO_SETUP_LONGCAT})."
  if [[ -x "${LONGCAT_VENV}/bin/python" ]]; then
    echo "[Runpod][LongCat-TTS] Existing venv found at ${LONGCAT_VENV}."
  else
    echo "[Runpod][LongCat-TTS] Venv not found. Run: bash scripts/setup_longcat_tts.sh"
  fi
fi
export LONGCAT_TTS_VENV="${LONGCAT_VENV}"
export LONGCAT_REPO_DIR="${LONGCAT_REPO}"

exec "${PYTHON_BIN}" scripts/start_codeagent.py \
  --host "${HOST}" \
  --port "${PORT}" \
  --primary-port "${PRIMARY_PORT}"
