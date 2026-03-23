#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/llama"
WORK_DIR="$(mktemp -d)"
EXTRACT_DIR="${WORK_DIR}/extract"
ARCHIVE_PATH="${WORK_DIR}/llama-vulkan.tar.gz"
BUILD_IF_NEEDED=0
FORCE_BUILD=0

# User-requested fixed asset URL (can be overridden by env if needed)
LLAMA_VULKAN_URL="${LLAMA_VULKAN_URL:-https://github.com/ggml-org/llama.cpp/releases/download/b8480/llama-b8480-bin-ubuntu-vulkan-x64.tar.gz}"

usage() {
  cat <<'USAGE'
Usage: setup_llama_runpod.sh [--build-if-needed] [--force-build]

  --build-if-needed  Build llama.cpp with Vulkan if prebuilt package verification fails.
  --force-build      Skip prebuilt package download and build from source immediately.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-if-needed)
      BUILD_IF_NEEDED=1
      ;;
    --force-build)
      FORCE_BUILD=1
      BUILD_IF_NEEDED=1
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

ensure_git() {
  if command -v git >/dev/null 2>&1; then
    return 0
  fi

  echo "[Runpod] git is missing. Installing git..."
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends git || {
      echo "[Runpod] Failed to install git via apt-get." >&2
      return 1
    }
    git --version
    return 0
  fi

  echo "[Runpod] apt-get is unavailable; cannot auto-install git." >&2
  return 1
}

install_prebuilt() {
  local asset_name
  asset_name="$(basename "${LLAMA_VULKAN_URL}")"

  echo "[Runpod] Downloading fixed Vulkan build: ${LLAMA_VULKAN_URL}"
  mkdir -p "${EXTRACT_DIR}"
  curl -fL --retry 3 --retry-delay 2 "${LLAMA_VULKAN_URL}" -o "${ARCHIVE_PATH}"

  tar -xzf "${ARCHIVE_PATH}" -C "${EXTRACT_DIR}"

  rm -rf "${OUT_DIR}"

  mapfile -t top_entries < <(find "${EXTRACT_DIR}" -mindepth 1 -maxdepth 1)
  if [[ "${#top_entries[@]}" -eq 1 && -d "${top_entries[0]}" ]]; then
    mv "${top_entries[0]}" "${OUT_DIR}"
  else
    mv "${EXTRACT_DIR}" "${OUT_DIR}"
  fi

  echo "[Runpod] Installed prebuilt llama.cpp Vulkan package into: ${OUT_DIR} (${asset_name})"
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
    if ! ldd "${llama_server}" | grep -qiE 'vulkan|libvulkan'; then
      echo "[Runpod] WARNING: Vulkan linkage was not detected via ldd." >&2
    fi
  fi

  echo "[Runpod] Runtime verification passed."
}

build_from_source() {
  echo "[Runpod] Building llama.cpp with Vulkan support from source..."

  if ! command -v cmake >/dev/null 2>&1; then
    echo "[Runpod] cmake is required for source build." >&2
    return 1
  fi
  ensure_git

  local src_dir build_dir
  src_dir="${WORK_DIR}/llama.cpp"
  build_dir="${src_dir}/build"

  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "${src_dir}"

  cmake -S "${src_dir}" -B "${build_dir}" \
    -DGGML_VULKAN=ON \
    -DGGML_NATIVE=OFF \
    -DCMAKE_BUILD_TYPE=Release

  cmake --build "${build_dir}" --config Release -j"$(nproc)"

  rm -rf "${OUT_DIR}"
  mkdir -p "${OUT_DIR}/bin"
  cp -a "${build_dir}/bin/." "${OUT_DIR}/bin/"

  if compgen -G "${build_dir}"'/*.so*' >/dev/null; then
    cp -a "${build_dir}"/*.so* "${OUT_DIR}/"
  fi

  echo "[Runpod] Source build installed into: ${OUT_DIR}"
}

if [[ "${FORCE_BUILD}" -eq 1 ]]; then
  build_from_source
  verify_runtime
  exit 0
fi

if install_prebuilt && verify_runtime; then
  exit 0
fi

echo "[Runpod] Prebuilt Vulkan package is not sufficient for this environment."
if [[ "${BUILD_IF_NEEDED}" -eq 1 ]]; then
  build_from_source
  verify_runtime
else
  echo "[Runpod] Re-run with --build-if-needed to compile llama.cpp." >&2
  exit 1
fi
