#!/usr/bin/env bash
set -euo pipefail

OUT="${1:-/workspace/ca_data/debug_runtime_snapshots/$(date -u +%Y%m%d-%H%M%S)}"
BASE_URL="${KASANECORE_BASE_URL:-http://127.0.0.1:8000}"
PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-/app/llama/bin/llama-server}"
mkdir -p "$OUT"

curl_json() {
  local name="$1"
  local url="$2"
  local tmp="$OUT/$name.raw"
  if curl -fsS --max-time 10 "$url" > "$tmp" 2> "$OUT/$name.curl.err"; then
    python -m json.tool < "$tmp" > "$OUT/$name.json" 2> "$OUT/$name.json.err" || cp "$tmp" "$OUT/$name.json"
  else
    {
      echo "curl failed for $url"
      cat "$OUT/$name.curl.err"
    } > "$OUT/$name.error.txt"
  fi
  rm -f "$tmp"
}

curl_json health "$BASE_URL/health"
curl_json system_summary "$BASE_URL/system/summary"
curl_json cuda_debug "$BASE_URL/runtime/cuda-debug"
curl_json audio_runtime_debug "$BASE_URL/audio/runtime/debug"
curl_json voice_status "$BASE_URL/voice/status"
curl_json models_db_status "$BASE_URL/models/db/status"
curl_json llm_ctx "$BASE_URL/llm/ctx"
curl_json llm_props "$BASE_URL/llm/props"
curl_json nexus_web_status "$BASE_URL/nexus/web/status"
curl_json echo_save_status "$BASE_URL/echo/save-status"

{
  echo "BASE_URL=$BASE_URL"
  echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
  echo "NVIDIA_VISIBLE_DEVICES=${NVIDIA_VISIBLE_DEVICES:-}"
  echo "NVIDIA_DRIVER_CAPABILITIES=${NVIDIA_DRIVER_CAPABILITIES:-}"
  echo "LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-}"
  echo "PYTHON_BIN=$PYTHON_BIN"
  echo "LLAMA_SERVER_BIN=$LLAMA_SERVER_BIN"
  echo "PATH=$PATH"
} > "$OUT/env.txt"

nvidia-smi > "$OUT/nvidia-smi.txt" 2>&1 || true
ls -l /dev/nvidia* > "$OUT/dev_nvidia.txt" 2>&1 || true

if [ -x "$PYTHON_BIN" ]; then
  "$PYTHON_BIN" - <<'PY' > "$OUT/python_cuda_probe.txt" 2>&1
import os
print("CUDA_VISIBLE_DEVICES=", os.environ.get("CUDA_VISIBLE_DEVICES"))
print("NVIDIA_VISIBLE_DEVICES=", os.environ.get("NVIDIA_VISIBLE_DEVICES"))
try:
    import torch
    print("torch", torch.__version__)
    print("torch.version.cuda", torch.version.cuda)
    print("torch.cuda.is_available", torch.cuda.is_available())
    print("torch.cuda.device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("torch.cuda.device_name", torch.cuda.get_device_name(0))
except Exception as e:
    print("torch error:", repr(e))
try:
    import ctranslate2
    print("ctranslate2", ctranslate2.__version__)
    print("ct2 cuda devices", ctranslate2.get_cuda_device_count())
    print("ct2 cuda compute types", ctranslate2.get_supported_compute_types("cuda"))
except Exception as e:
    print("ctranslate2 error:", repr(e))
PY
else
  echo "Python binary not executable: $PYTHON_BIN" > "$OUT/python_cuda_probe.txt"
fi

"$LLAMA_SERVER_BIN" --version > "$OUT/llama_version.txt" 2>&1 || true
ldd "$LLAMA_SERVER_BIN" > "$OUT/llama_ldd.txt" 2>&1 || true
strings "$LLAMA_SERVER_BIN" | grep -E -i 'ggml_cuda|cublas|cuda' | head -100 > "$OUT/llama_cuda_strings.txt" 2>&1 || true

{
  echo "# ps aux tail"
  ps aux 2>&1 | tail -100 || true
  echo
  echo "# /workspace/ca_data log tails"
  find /workspace/ca_data -maxdepth 4 -type f \( -name '*.log' -o -name '*log*.txt' \) -print 2>/dev/null | sort | tail -20 | while read -r log_file; do
    echo "## $log_file"
    tail -200 "$log_file" 2>&1 || true
  done
  echo
  echo "# container stdout/stderr tail best-effort"
  if command -v timeout >/dev/null 2>&1; then
    timeout 2s tail -200 /proc/1/fd/1 2>&1 || true
    timeout 2s tail -200 /proc/1/fd/2 2>&1 || true
  else
    echo "timeout command unavailable; skipping /proc/1 fd tails to avoid blocking"
  fi
} > "$OUT/container_log_tail.txt" 2>&1 || true

cat > "$OUT/README.txt" <<EOF_README
Runtime snapshot collected at: $OUT
Base URL: $BASE_URL

Attach this directory when reporting Runpod/CUDA/LLM/ASR/TTS failures.
Start with docs/runbooks/runpod_cuda_recovery.md and docs/runbooks/known_good_runtime_baseline.md.
EOF_README

echo "$OUT"
