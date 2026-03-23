#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/llama"
WORK_DIR="$(mktemp -d)"
ARCHIVE_PATH="${WORK_DIR}/llama-linux-cuda-archive"
EXTRACT_DIR="${WORK_DIR}/extract"
BUILD_IF_NEEDED=0
FORCE_BUILD=0
INSTALL_PYTHON_CUDA=1

LLAMA_CPP_WHL_INDEX_URL="${LLAMA_CPP_WHL_INDEX_URL:-https://abetlen.github.io/llama-cpp-python/whl/cu124}"

usage() {
  cat <<'USAGE'
Usage: setup_llama_runpod.sh [--build-if-needed] [--force-build] [--skip-python-wheel]

  --build-if-needed  Build llama.cpp with CUDA if prebuilt package verification fails.
  --force-build      Skip prebuilt package download and build from source immediately.
  --skip-python-wheel  Skip llama-cpp-python CUDA wheel validation/installation.
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
    --skip-python-wheel)
      INSTALL_PYTHON_CUDA=0
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

resolve_prebuilt_asset() {
  python - <<'PY'
import json
import re
import urllib.request

url = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
req = urllib.request.Request(url, headers={"User-Agent": "codeagent-runpod-setup"})
with urllib.request.urlopen(req) as response:
    payload = json.load(response)

assets = payload.get("assets", [])
pattern = re.compile(r"(linux|ubuntu).*(cuda).*x64.*\\.(zip|tar\\.gz|tgz)$", re.IGNORECASE)
matches = [a for a in assets if pattern.search(a.get("name", ""))]
if not matches:
    raise SystemExit("No Linux CUDA x64 llama.cpp zip asset found in latest release.")

matches.sort(key=lambda asset: asset.get("name", ""), reverse=True)
selected = matches[0]
print(selected["browser_download_url"])
print(selected["name"])
PY
}

extract_prebuilt_archive() {
  local archive_path="$1"
  local asset_name="$2"
  local lower_name
  lower_name="$(echo "${asset_name}" | tr '[:upper:]' '[:lower:]')"

  mkdir -p "${EXTRACT_DIR}"
  if [[ "${lower_name}" == *.zip ]]; then
    python - "${archive_path}" "${EXTRACT_DIR}" <<'PY'
import pathlib
import sys
import zipfile

zip_path = pathlib.Path(sys.argv[1])
extract_dir = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(extract_dir)
PY
  elif [[ "${lower_name}" == *.tar.gz || "${lower_name}" == *.tgz ]]; then
    tar -xzf "${archive_path}" -C "${EXTRACT_DIR}"
  else
    echo "[Runpod] Unsupported prebuilt archive format: ${asset_name}" >&2
    return 1
  fi
}

install_prebuilt() {
  echo "[Runpod] Resolving latest llama.cpp Linux CUDA build..."
  local asset_info download_url asset_name
  asset_info="$(resolve_prebuilt_asset)"

  download_url="$(echo "${asset_info}" | sed -n '1p')"
  asset_name="$(echo "${asset_info}" | sed -n '2p')"

  if [[ -z "${download_url}" || -z "${asset_name}" ]]; then
    echo "[Runpod] Failed to resolve download URL for llama.cpp Linux CUDA package."
    return 1
  fi

  echo "[Runpod] Downloading ${asset_name}..."
  local archive_path="${ARCHIVE_PATH}.${asset_name##*.}"
  curl -fL --retry 3 --retry-delay 2 "${download_url}" -o "${archive_path}"
  extract_prebuilt_archive "${archive_path}" "${asset_name}"

  rm -rf "${OUT_DIR}"

  mapfile -t top_entries < <(find "${EXTRACT_DIR}" -mindepth 1 -maxdepth 1)
  if [[ "${#top_entries[@]}" -eq 1 && -d "${top_entries[0]}" ]]; then
    mv "${top_entries[0]}" "${OUT_DIR}"
  else
    mv "${EXTRACT_DIR}" "${OUT_DIR}"
  fi

  echo "[Runpod] Installed prebuilt llama.cpp Linux CUDA package into: ${OUT_DIR}"
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

verify_cuda_runtime() {
  local llama_server
  llama_server="$(resolve_llama_server || true)"
  if [[ -z "${llama_server}" ]]; then
    echo "[Runpod] llama-server executable was not found under ${OUT_DIR}."
    return 1
  fi

  echo "[Runpod] Verifying llama-server: ${llama_server}"
  "${llama_server}" --version >/dev/null

  if command -v ldd >/dev/null 2>&1; then
    if ! ldd "${llama_server}" | grep -qiE 'libcudart|libcuda'; then
      echo "[Runpod] llama-server is missing CUDA runtime linkage (libcudart/libcuda)."
      return 1
    fi
  fi

  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
  else
    echo "[Runpod] nvidia-smi not found; cannot fully validate CUDA runtime." >&2
    return 1
  fi

  echo "[Runpod] CUDA runtime verification passed."
}

build_from_source() {
  echo "[Runpod] Building llama.cpp with CUDA support from source..."

  if ! command -v cmake >/dev/null 2>&1; then
    echo "[Runpod] cmake is required for source build." >&2
    return 1
  fi
  if ! command -v git >/dev/null 2>&1; then
    echo "[Runpod] git is required for source build." >&2
    return 1
  fi

  local src_dir build_dir
  src_dir="${WORK_DIR}/llama.cpp"
  build_dir="${src_dir}/build"

  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "${src_dir}"

  cmake -S "${src_dir}" -B "${build_dir}" \
    -DGGML_CUDA=ON \
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

resolve_python311() {
  if command -v python3.11 >/dev/null 2>&1; then
    echo "python3.11"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    local version
    version="$(python - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
    if [[ "${version}" == "3.11" ]]; then
      echo "python"
      return 0
    fi
  fi
  return 1
}

python_wheel_has_cuda() {
  local pybin="$1"
  local ext_path
  ext_path="$(${pybin} - <<'PY'
import importlib.util
import pathlib
import sys

spec = importlib.util.find_spec("llama_cpp._llama_cpp")
if spec and spec.origin:
    print(pathlib.Path(spec.origin))
else:
    sys.exit(1)
PY
  )" || return 1

  if [[ -z "${ext_path}" || ! -f "${ext_path}" ]]; then
    return 1
  fi

  if command -v ldd >/dev/null 2>&1; then
    ldd "${ext_path}" | grep -qiE 'libcudart|libcuda'
    return $?
  fi

  return 1
}

install_llama_cpp_python_cuda() {
  local pybin="$1"
  echo "[Runpod] Installing llama-cpp-python CUDA wheel for Python 3.11..."
  "${pybin}" -m pip install --upgrade pip
  "${pybin}" -m pip install --upgrade --extra-index-url "${LLAMA_CPP_WHL_INDEX_URL}" llama-cpp-python
}

ensure_llama_cpp_python_cuda() {
  if [[ "${INSTALL_PYTHON_CUDA}" -eq 0 ]]; then
    echo "[Runpod] Skipping llama-cpp-python CUDA wheel setup (--skip-python-wheel)."
    return 0
  fi

  local pybin
  pybin="$(resolve_python311 || true)"
  if [[ -z "${pybin}" ]]; then
    echo "[Runpod] Python 3.11 was not found; skipping llama-cpp-python CUDA wheel setup." >&2
    return 1
  fi

  echo "[Runpod] Validating llama-cpp-python CUDA wheel on ${pybin}..."
  if python_wheel_has_cuda "${pybin}"; then
    echo "[Runpod] llama-cpp-python CUDA wheel is already available for Python 3.11."
    return 0
  fi

  install_llama_cpp_python_cuda "${pybin}"

  if python_wheel_has_cuda "${pybin}"; then
    echo "[Runpod] llama-cpp-python CUDA wheel installation verified."
    return 0
  fi

  echo "[Runpod] Failed to verify CUDA linkage in llama-cpp-python for Python 3.11." >&2
  return 1
}

if [[ "${FORCE_BUILD}" -eq 1 ]]; then
  build_from_source
  verify_cuda_runtime
  ensure_llama_cpp_python_cuda
  exit 0
fi

if install_prebuilt && verify_cuda_runtime; then
  ensure_llama_cpp_python_cuda
  exit 0
fi

echo "[Runpod] Prebuilt CUDA package is not sufficient for this environment."
if [[ "${BUILD_IF_NEEDED}" -eq 1 ]]; then
  build_from_source
  verify_cuda_runtime
  ensure_llama_cpp_python_cuda
else
  echo "[Runpod] Re-run with --build-if-needed to compile llama.cpp during CI/Actions." >&2
  exit 1
fi
