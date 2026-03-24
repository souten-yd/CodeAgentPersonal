#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/llama"
WORK_DIR="$(mktemp -d)"
BUILD_DIR="${WORK_DIR}/llama.cpp/build"
ARCHIVE_PATH="${WORK_DIR}/llama-cuda-prebuilt.tar.gz"
EXTRACT_DIR="${WORK_DIR}/extract"
FORCE_BUILD=0
CUDA_EXTRA_FLAGS="${LLAMA_CUDA_FLAGS:--Wno-deprecated-gpu-targets}"
CUDA_PREBUILT_URL="${LLAMA_CUDA_PREBUILT_URL:-}"

usage() {
  cat <<'USAGE'
Usage: setup_llama_runpod.sh [--force-build] [--build-if-needed]

  --force-build      Rebuild llama.cpp CUDA binaries even when existing output is valid.
  --build-if-needed  Backward-compatible alias; CUDA source build is now the default.

Environment:
  LLAMA_CUDA_PREBUILT_URL  Optional CUDA prebuilt tar.gz URL. If set, download/extract is tried first.
  LLAMA_CUDA_FLAGS         Extra CUDA compiler flags (default: -Wno-deprecated-gpu-targets).
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force-build)
      FORCE_BUILD=1
      ;;
    --build-if-needed)
      # Backward compatibility: this script now always builds from source when prebuilt is not specified.
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

install_prebuilt() {
  if [[ -z "${CUDA_PREBUILT_URL}" ]]; then
    return 1
  fi

  echo "[Runpod] Trying CUDA prebuilt package: ${CUDA_PREBUILT_URL}"
  ensure_tool curl
  ensure_tool tar

  mkdir -p "${EXTRACT_DIR}"
  curl -fL --retry 3 --retry-delay 2 "${CUDA_PREBUILT_URL}" -o "${ARCHIVE_PATH}"
  tar -xzf "${ARCHIVE_PATH}" -C "${EXTRACT_DIR}"

  rm -rf "${OUT_DIR}"
  mapfile -t top_entries < <(find "${EXTRACT_DIR}" -mindepth 1 -maxdepth 1)
  if [[ "${#top_entries[@]}" -eq 1 && -d "${top_entries[0]}" ]]; then
    mv "${top_entries[0]}" "${OUT_DIR}"
  else
    mv "${EXTRACT_DIR}" "${OUT_DIR}"
  fi

  echo "[Runpod] CUDA prebuilt package installed into: ${OUT_DIR}"
}

build_from_source() {
  echo "[Runpod] Building latest llama.cpp with CUDA support from source..."

  ensure_tool git
  ensure_tool cmake
  ensure_tool g++

  if ! command -v nvcc >/dev/null 2>&1; then
    echo "[Runpod][WARN] nvcc not found. Use a CUDA devel image (e.g. nvidia/cuda:* -devel) for build." >&2
  fi

  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "${WORK_DIR}/llama.cpp"

  cmake -S "${WORK_DIR}/llama.cpp" -B "${BUILD_DIR}" \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES=native \
    -DCMAKE_CUDA_FLAGS="${CUDA_EXTRA_FLAGS}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_CURL=ON \
    -DLLAMA_SERVER=ON

  cmake --build "${BUILD_DIR}" --config Release -j"$(nproc)"

  rm -rf "${OUT_DIR}"
  mkdir -p "${OUT_DIR}/bin"
  cp -a "${BUILD_DIR}/bin/." "${OUT_DIR}/bin/"

  if compgen -G "${BUILD_DIR}"'/*.so*' >/dev/null; then
    cp -a "${BUILD_DIR}"/*.so* "${OUT_DIR}/"
  fi

  echo "[Runpod] CUDA source build installed into: ${OUT_DIR}"
}

if [[ "${FORCE_BUILD}" -eq 0 ]] && verify_runtime; then
  echo "[Runpod] Existing CUDA llama build is valid. Use --force-build to rebuild."
  exit 0
fi

if [[ "${FORCE_BUILD}" -eq 0 ]] && install_prebuilt && verify_runtime; then
  exit 0
fi

build_from_source
verify_runtime
