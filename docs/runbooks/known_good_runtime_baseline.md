# Known-good Runtime Baseline

この文書は `KasaneCore_v2.7` と `PR4.50.1 / #963` 後の正常復旧状態を、壊れた時に比較するための baseline として記録します。

## Baseline identity

- Baseline name: `post-PR4.50.1`
- Recovery references:
  - `KasaneCore_v2.7`: CUDA 正常基準
  - `PR4.50.1 / #963`: LLM / ASR / TTS 正常復旧ポイント
- Snapshot command:

```bash
bash scripts/collect_runtime_snapshot.sh
```

## Docker / Runpod / CUDA expectations

- Runpod container から NVIDIA device が見える。
- `nvidia-smi` が成功する。
- `/dev/nvidia*` が存在する。
- `CUDA_VISIBLE_DEVICES` / `NVIDIA_VISIBLE_DEVICES` が GPU を隠していない。
- `torch.cuda.is_available()` が正常に評価でき、`CUDA initialization: CUDA unknown error` を出さない。
- `ctranslate2` の CUDA device count / compute types が取得できる。

## llama / LLM expectations

- Runpod Linux では `-ngl` 明示探索を行う。
- 正常ログ例:

```text
Runpod/Linux explicit search start high=999
try -ngl=999 -> OK
final -ngl=999 parsed_n_gpu_layers=43
[OK] LLM ready
[LLM] Warm-up complete
```

- `llama-server --version` が取得できる。
- `ldd /app/llama/bin/llama-server` で CUDA / cuBLAS / cudart の missing がない。
- `strings /app/llama/bin/llama-server` で CUDA 関連 symbol 文字列が確認できる。

## ASR expectations

- ASR は明示 load / transcribe 操作時に CUDA / float16 経路を使える。
- `/voice/status` は状態確認のみで CUDA probe しない。
- 異常時の CPU/int8 fallback は、手動確認と snapshot で原因を分ける。

## TTS expectations

- SBV2 TTS が明示 load / synthesize 操作時に成功する。
- TTS status endpoint は import-time / status-time の heavy CUDA probe をしない。

## 正常時の lightweight endpoint 出力例

`check_runtime_baseline.py` は LLM/ASR/TTS 実行を強制せず、軽量 endpoint の到達性と説明可能な runtime 状態だけを確認します。

```json
{
  "health": {"status": "ok"},
  "runtime_cuda_debug": {
    "baseline_ref": "KasaneCore_v2.7",
    "runpod_detected": true,
    "intended_backend": "cuda",
    "import_time_probe_detected": false
  },
  "voice_status": {"ok": true},
  "audio_runtime_debug": {"runtime": "gpu"},
  "nexus_web_status": {"enabled": true},
  "echo_save_status": {"ok": true}
}
```

実際の response shape は production provider に従います。この例は正常時の意味を示す抜粋です。

## 正常時の起動ログ抜粋

```text
Runpod/Linux explicit search start high=999
try -ngl=999 -> OK
final -ngl=999 parsed_n_gpu_layers=43
[OK] LLM ready
[LLM] Warm-up complete
ASR CUDA success
SBV2 TTS success
```

## 必ず守る invariant

- `main.py` import 時に `detect_audio_runtime()` を呼ばない。
- `app.server` は top-level で router を大量 import しない。
- `app/server.py` の router import は `include_routers()` 内で lazy import する。
- `/voice/status` は CUDA probe しない。
- ASR/TTS/LLM CUDA probe は明示操作時だけ行う。
- `create_app()` fallback は CUDA / filesystem heavy scan / model load をしない。

## Baseline を更新してよい条件

- Runpod / CUDA / LLM / ASR / TTS が明示確認済みである。
- `bash scripts/collect_runtime_snapshot.sh` の出力が保存されている。
- 上記 invariant を破っていない。
- 新 baseline の PR に、旧 baseline との差分と rollback 判断を記録している。
