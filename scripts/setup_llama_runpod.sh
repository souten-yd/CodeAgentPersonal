#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/llama"
WORK_DIR="$(mktemp -d)"
FORCE_PREBUILT_REFRESH=0
GITHUB_API_URL="https://api.github.com/repos/ai-dock/llama.cpp-cuda/releases/latest"
ASSET_REGEX='^llama\.cpp-b[0-9]+-cuda-12\.8\.tar\.gz$'

usage() {
  cat <<'USAGE'
Usage: setup_llama_runpod.sh [--refresh-prebuilt] [--install-if-needed]

  --refresh-prebuilt Re-download and reinstall the latest ai-dock prebuilt even when existing output is valid.
  --install-if-needed Preferred no-op alias for default behavior (install only when needed).
  --force-build      Backward-compatible alias for --refresh-prebuilt.
  --build-if-needed  Backward-compatible alias for --install-if-needed.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --refresh-prebuilt)
      FORCE_PREBUILT_REFRESH=1
      ;;
    --install-if-needed)
      ;;
    --force-build)
      FORCE_PREBUILT_REFRESH=1
      echo "[Runpod][WARN] --force-build is deprecated; use --refresh-prebuilt." >&2
      ;;
    --build-if-needed)
      echo "[Runpod][WARN] --build-if-needed is deprecated; use --install-if-needed." >&2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[Runpod] Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

cleanup() {
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

ensure_tool() {
  local tool="$1"
  if command -v "${tool}" >/dev/null 2>&1; then
    return 0
  fi

  echo "[Runpod] ${tool} is missing. Installing ${tool}..."
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "[Runpod] apt-get is unavailable; cannot auto-install ${tool}." >&2
    return 1
  fi

  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends "${tool}" || {
    echo "[Runpod] Failed to install ${tool} via apt-get." >&2
    return 1
  }
}

resolve_llama_server() {
  local candidate
  for candidate in \
    "${OUT_DIR}/llama-server" \
    "${OUT_DIR}/bin/llama-server" \
    "${OUT_DIR}/build/bin/llama-server"
  do
    if [[ -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

verify_runtime() {
  local llama_server
  llama_server="$(resolve_llama_server || true)"
  if [[ -z "${llama_server}" ]]; then
    echo "[Runpod] llama-server executable was not found under ${OUT_DIR}." >&2
    return 1
  fi

  echo "[Runpod] Verifying llama-server: ${llama_server}"
  "${llama_server}" --version >/dev/null

  if command -v ldd >/dev/null 2>&1; then
    if ! ldd "${llama_server}" | grep -qiE 'cuda|cudart|cublas|nvidia'; then
      echo "[Runpod] WARNING: CUDA linkage was not detected via ldd." >&2
    fi
  fi

  echo "[Runpod] CUDA runtime verification passed."
}

select_release_asset() {
  local release_json="$1"
  python3 - "${release_json}" "${ASSET_REGEX}" <<'PY'
import json
import re
import sys

release = json.loads(sys.argv[1])
pattern = re.compile(sys.argv[2])

for asset in release.get("assets", []):
    name = asset.get("name", "")
    if pattern.match(name):
        print(asset.get("browser_download_url", ""))
        print(name)
        raise SystemExit(0)

raise SystemExit(1)
PY
}

install_latest_prebuilt() {
  echo "[Runpod] Fetching latest ai-dock llama.cpp CUDA prebuilt..."

  ensure_tool curl
  ensure_tool tar
  ensure_tool python3

  local release_json
  release_json="$(curl -fsSL "${GITHUB_API_URL}")"

  local selected
  if ! selected="$(select_release_asset "${release_json}")"; then
    echo "[Runpod] Failed to find asset matching ${ASSET_REGEX} in latest release." >&2
    return 1
  fi

  local asset_url asset_name
  asset_url="$(echo "${selected}" | sed -n '1p')"
  asset_name="$(echo "${selected}" | sed -n '2p')"
  if [[ -z "${asset_url}" || -z "${asset_name}" ]]; then
    echo "[Runpod] Failed to parse matched asset information." >&2
    return 1
  fi

  echo "[Runpod] Selected latest asset: ${asset_name}"
  local archive_path="${WORK_DIR}/${asset_name}"
  local extract_dir="${WORK_DIR}/extract"
  mkdir -p "${extract_dir}"

  curl -fL "${asset_url}" -o "${archive_path}"
  tar -xzf "${archive_path}" -C "${extract_dir}"

  local llama_server llama_cli source_root
  llama_server="$(find "${extract_dir}" -type f -name 'llama-server' -perm -u+x | head -n1 || true)"
  llama_cli="$(find "${extract_dir}" -type f -name 'llama-cli' -perm -u+x | head -n1 || true)"
  if [[ -z "${llama_server}" || -z "${llama_cli}" ]]; then
    echo "[Runpod] Extracted archive did not contain expected executables." >&2
    return 1
  fi
  source_root="$(dirname "${llama_server}")"

  rm -rf "${OUT_DIR}"
  mkdir -p "${OUT_DIR}"
  cp -a "${source_root}/." "${OUT_DIR}/"

  if [[ ! -x "${OUT_DIR}/llama-server" ]]; then
    cp -a "${llama_server}" "${OUT_DIR}/llama-server"
  fi
  if [[ ! -x "${OUT_DIR}/llama-cli" ]]; then
    cp -a "${llama_cli}" "${OUT_DIR}/llama-cli"
  fi

  mkdir -p "${OUT_DIR}/bin"
  cp -a "${OUT_DIR}/llama-server" "${OUT_DIR}/bin/llama-server"
  cp -a "${OUT_DIR}/llama-cli" "${OUT_DIR}/bin/llama-cli"

  if ! find "${OUT_DIR}" -type f -name '*.so*' | grep -q .; then
    echo "[Runpod][WARN] No shared libraries (*.so*) were found in the extracted archive." >&2
  fi

  echo "[Runpod] Latest CUDA prebuilt installed into: ${OUT_DIR}"
}

if [[ "${FORCE_PREBUILT_REFRESH}" -eq 0 ]] && verify_runtime; then
  echo "[Runpod] Existing CUDA llama prebuilt is valid. Use --refresh-prebuilt to reinstall."
  exit 0
fi

install_latest_prebuilt
verify_runtime
