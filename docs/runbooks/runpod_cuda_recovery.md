# Runpod / CUDA Recovery Runbook

目的: Runpod / CUDA / LLM / ASR / TTS が壊れた時に、最初に同じ情報を集め、正常基準との差分を見て、ロールバック候補を素早く決めるための復旧 runbook です。

## Known-good baseline

- `KasaneCore_v2.7` は CUDA 正常基準です。
- `PR4.50.1 / #963` 後、LLM / ASR / TTS は正常復旧した状態を基準にします。
- この PR4.50.2 は機能分割を進めません。Nexus / Jobs / Echo / Model runtime の実装変更ではなく、復旧用メモ・機能一覧・正常時スナップショット取得の整備だけを目的にします。

## 正常ログ例

正常時は以下のようなログ・状態になります。

```text
# torch CUDA unknown error が出ない
Runpod/Linux explicit search start high=999
try -ngl=999 -> OK
final -ngl=999 parsed_n_gpu_layers=43
Runpod/Linux GPU validation accepted without n_gpu_layers
accepted_new_llama_device_info_format
CUDA0 detected
model_loaded=True server_listening=True
[OK] LLM ready
[LLM] Warm-up complete
ASR CUDA success / ASR CUDA 成功
SBV2 TTS success / SBV2 TTS 成功
```

期待する意味:

- `torch CUDA unknown error` が出ない。
- Runpod Linux では明示的な `-ngl` 探索が `high=999` から開始される。
- `try -ngl=999 -> OK` になり、最終的に `final -ngl=999 parsed_n_gpu_layers=43` が記録される。
- LLM は `[OK] LLM ready` と `[LLM] Warm-up complete` まで進む。
- ASR は CUDA / float16 経路で成功する。
- TTS は SBV2 経路で成功する。

## 異常ログ例

以下が出た場合は、CUDA の可視性、import-time probe、llama-server の CUDA linkage、Runpod の GPU injection、ASR/TTS の backend 選択を疑います。

```text
CUDA initialization: CUDA unknown error
Setting available devices to zero
CUDA buffer not detected
nvidia-smi memory did not increase
ASR CUDA initialization failed; falling back to CPU/int8
```


## ModelManager parser stale / llama.cpp log format drift

以下なら Runpod GPU / CUDA 自体は正常で、ModelManager parser false negative（または llama.cpp のログ形式変更）を疑います。

- `cuInit rc 0`
- `torch.cuda.is_available True`
- `/app/llama/bin/llama-server --version` で `ggml_cuda_init failed` が出ない
- 手動 `llama-server` 起動で以下が出る
  - `CUDA0 : ...`
  - `system_info: ... CUDA : ARCHS ...`
  - `model loaded`
  - `server is listening`
- CodeAgent auto-load では以下で失敗する
  - `CUDA buffer not detected`
  - `GPU offload layers not detected`
  - `n_gpu_layers not detected`
- `llama_startup.log` には `model loaded` / `server is listening` があるのに、その直後に `cleaning up before exit` がある

以下なら ModelManager parser ではなく、Runpod ホスト / NVIDIA container runtime / GPU attach 異常を疑います。

- `cuInit rc 999`
- `torch.cuda.is_available False`
- `llama-server --version` で `ggml_cuda_init: failed to initialize CUDA`
- `no usable GPU found`

調査コマンド:

```bash
echo "=== CUDA preflight ==="
export NVIDIA_DRIVER_CAPABILITIES="${NVIDIA_DRIVER_CAPABILITIES:-all}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-all}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

nvidia-smi
ls -l /dev/nvidia* || true

/opt/venv/bin/python - <<'PY'
import os, ctypes, ctypes.util, torch
print("CUDA_VISIBLE_DEVICES", os.environ.get("CUDA_VISIBLE_DEVICES"))
print("NVIDIA_VISIBLE_DEVICES", os.environ.get("NVIDIA_VISIBLE_DEVICES"))
print("NVIDIA_DRIVER_CAPABILITIES", os.environ.get("NVIDIA_DRIVER_CAPABILITIES"))
print("torch", torch.__version__)
print("torch.version.cuda", torch.version.cuda)
print("torch.cuda.is_available", torch.cuda.is_available())
print("torch.cuda.device_count", torch.cuda.device_count())
if torch.cuda.is_available():
    print("torch.cuda.device_name", torch.cuda.get_device_name(0))
cuda = ctypes.CDLL(ctypes.util.find_library("cuda") or "libcuda.so.1")
print("cuInit rc", cuda.cuInit(0))
PY

echo "=== llama startup log ==="
LOG=/workspace/ca_data/Logs/llama_startup.log
tail -n 180 "$LOG" 2>/dev/null || true
grep -nEi "CUDA0|CUDA|gpu|n_gpu|offload|buffer|model loaded|server is listening|failed|error|no usable|device_info|system_info|load_model|cleaning up" "$LOG" 2>/dev/null | tail -180 || true
```

正常判定例は旧形式の `final -ngl=999 parsed_n_gpu_layers=43` だけではありません。新しい llama.cpp ログでは以下も正常として扱います。

- `Runpod/Linux GPU validation accepted without n_gpu_layers`
- `accepted_new_llama_device_info_format`
- `CUDA0 detected`
- `model_loaded=True`
- `server_listening=True`

## 最初に貼るべきコマンド

障害報告では、まず次を実行し、出力されたディレクトリパスと中身を貼ります。

```bash
bash scripts/collect_runtime_snapshot.sh
```

必要に応じて出力先を固定します。

```bash
bash scripts/collect_runtime_snapshot.sh /workspace/ca_data/debug_runtime_snapshots/manual-$(date -u +%Y%m%d-%H%M%S)
```

追加で軽量 baseline check だけ確認する場合:

```bash
python scripts/check_runtime_baseline.py
```

## 原因切り分け順

1. **Runpod GPU injection の確認**
   - `nvidia-smi.txt` が GPU を見つけているか。
   - `dev_nvidia.txt` に `/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-uvm` があるか。
   - `env.txt` の `CUDA_VISIBLE_DEVICES` / `NVIDIA_VISIBLE_DEVICES` が空・不正値・意図しないマスクになっていないか。
2. **Python CUDA stack の確認**
   - `python_cuda_probe.txt` で `torch.cuda.is_available()` と `torch.cuda.device_count()` を確認する。
   - `ctranslate2.get_cuda_device_count()` と `get_supported_compute_types("cuda")` を確認する。
3. **llama-server CUDA linkage の確認**
   - `llama_version.txt` で実行ファイルが想定版か。
   - `llama_ldd.txt` に `cuda`, `cublas`, `cudart` の解決失敗がないか。
   - `llama_cuda_strings.txt` に `ggml_cuda`, `cublas`, `cuda` などの CUDA 文字列が残っているか。
4. **軽量 endpoint の確認**
   - `health.json`, `system_summary.json`, `cuda_debug.json`, `audio_runtime_debug.json`, `voice_status.json` を確認する。
   - `/voice/status` は CUDA probe しないため、ここで heavy probe が発生していたら regression とみなす。
5. **LLM Runpod `-ngl` 探索の確認**
   - 起動ログに `Runpod/Linux explicit search start high=999` があるか。
   - `try -ngl=999 -> OK` と `final -ngl=999 parsed_n_gpu_layers=43` があるか。
6. **ASR / TTS の明示操作時だけ確認**
   - ASR/TTS/LLM CUDA probe は明示操作時だけ行う。
   - 自動 snapshot では LLM/ASR/TTS の実行までは強制しない。

## 戻すべき変更候補

壊れた場合は、まず以下を疑います。

- `main.py` import 時に `detect_audio_runtime()` を呼ぶ変更。
- `app.server` が top-level で router を大量 import する変更。
- `app/server.py` の router import が `include_routers()` 内の lazy import ではなくなる変更。
- `/voice/status` が CUDA probe する変更。
- ASR/TTS/LLM CUDA probe を import 時・status endpoint・`create_app()` fallback で実行する変更。
- `create_app()` fallback が CUDA / filesystem heavy scan / model load を実行する変更。
- Runpod Linux の `-ngl=999` 明示探索や `parsed_n_gpu_layers=43` 確認を弱める変更。
- ModelManager 探索ロジック、llama-server 起動オプション、Docker CUDA stack の変更。

## 復旧判断の目安

- `KasaneCore_v2.7` と `PR4.50.1 / #963` を復旧ポイントとして扱います。
- snapshot で GPU device / torch / ctranslate2 / llama linkage が壊れていれば runtime 環境・Docker・Runpod 起因を優先します。
- snapshot が正常なのに LLM 起動だけ失敗する場合は ModelManager / llama-server `-ngl` 探索を優先します。
- snapshot が正常なのに ASR/TTS だけ CPU fallback する場合は audio runtime 選択と SBV2 / ctranslate2 の依存関係を優先します。
