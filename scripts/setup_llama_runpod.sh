#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/llama"
WORK_DIR="$(mktemp -d)"
ZIP_PATH="${WORK_DIR}/llama-linux-cuda.zip"
EXTRACT_DIR="${WORK_DIR}/extract"

cleanup() {
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

echo "[Runpod] Resolving latest llama.cpp Linux CUDA build..."
ASSET_INFO="$({
  python - <<'PY'
import json
import re
import urllib.request

url = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
req = urllib.request.Request(url, headers={"User-Agent": "codeagent-runpod-setup"})
with urllib.request.urlopen(req) as response:
    payload = json.load(response)

assets = payload.get("assets", [])
pattern = re.compile(r"(linux|ubuntu).*(cuda).*x64.*\\.zip$", re.IGNORECASE)
matches = [a for a in assets if pattern.search(a.get("name", ""))]
if not matches:
    raise SystemExit("No Linux CUDA x64 llama.cpp zip asset found in latest release.")

matches.sort(key=lambda asset: asset.get("name", ""), reverse=True)
selected = matches[0]
print(selected["browser_download_url"])
print(selected["name"])
PY
} )"

DOWNLOAD_URL="$(echo "${ASSET_INFO}" | sed -n '1p')"
ASSET_NAME="$(echo "${ASSET_INFO}" | sed -n '2p')"

if [[ -z "${DOWNLOAD_URL}" || -z "${ASSET_NAME}" ]]; then
  echo "[Runpod] Failed to resolve download URL for llama.cpp Linux CUDA package."
  exit 1
fi

echo "[Runpod] Downloading ${ASSET_NAME}..."
curl -fL --retry 3 --retry-delay 2 "${DOWNLOAD_URL}" -o "${ZIP_PATH}"

mkdir -p "${EXTRACT_DIR}"
python - "${ZIP_PATH}" "${EXTRACT_DIR}" <<'PY'
import pathlib
import sys
import zipfile

zip_path = pathlib.Path(sys.argv[1])
extract_dir = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(extract_dir)
PY

rm -rf "${OUT_DIR}"

mapfile -t top_entries < <(find "${EXTRACT_DIR}" -mindepth 1 -maxdepth 1)
if [[ "${#top_entries[@]}" -eq 1 && -d "${top_entries[0]}" ]]; then
  mv "${top_entries[0]}" "${OUT_DIR}"
else
  mv "${EXTRACT_DIR}" "${OUT_DIR}"
fi

echo "[Runpod] Installed llama.cpp Linux CUDA package into: ${OUT_DIR}"
