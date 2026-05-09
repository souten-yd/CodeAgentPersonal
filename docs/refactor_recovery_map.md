# Refactor Recovery Map

この map は「どの PR で何を分離したか」と「壊れた時にどこを見るか」をまとめる復旧用メモです。

## PR4.46

- 変更:
  - Nexus read-only を `app/api/nexus.py` へ分離。
  - summary / documents / active jobs / web status の fallback/provider 境界を作成。
- 壊れた時に見る場所:
  - `app/api/nexus.py`
  - `main.py` の provider registration
  - Nexus read-only fallback が heavy runtime に触っていないか

## PR4.47

- 変更:
  - Echo read-only を `app/api/echo.py` へ分離。
  - save-status / sessions の fallback/provider 境界を作成。
- 壊れた時に見る場所:
  - `app/api/echo.py`
  - `main.py` の Echo provider registration
  - `/echo/stream` と read-only sessions を混同していないか

## PR4.48

- 変更:
  - runtime lightweight write controls を `app/api/runtime_controls.py` へ分離。
  - search / streaming / llm ctx / CUDA debug / audio runtime debug の fallback/provider 境界を作成。
- 壊れた時に見る場所:
  - `app/api/runtime_controls.py`
  - `main.py` の runtime provider registration
  - fallback が CUDA / filesystem heavy scan / model load をしていないか

## PR4.49

- 変更:
  - job execution body を `app/services/jobs.py` へ分離。
  - router と service の責務を分ける準備。
- 壊れた時に見る場所:
  - `app/services/jobs.py`
  - job execution が `main.py` import に戻っていないか
  - LLM / web search / job persistence の境界

## PR4.50

- 変更:
  - `POST /jobs/submit` を `app/api/jobs.py` へ分離。
  - app-factory fallback と production provider を追加。
- 壊れた時に見る場所:
  - `app/api/jobs.py`
  - `app/services/jobs.py`
  - `main.py` の `job_submit_provider`
  - fallback が background thread / LLM / filesystem / ASR / TTS を起動していないか

## PR4.50.1

- 変更:
  - CUDA import-time probe 回避。
  - `main.py` import時 `detect_audio_runtime()` 禁止。
  - `app.server` lazy router import。
  - `app/server.py` の router import を `include_routers()` 内に閉じ込め。
- 壊れた時に見る場所:
  - `main.py` の音声 runtime 初期化 section。
  - `app/server.py` の top-level imports と `include_routers()`。
  - `tests/test_no_import_time_cuda_probe_contract.py`。
  - `docs/runbooks/known_good_runtime_baseline.md` の invariant。

## PR4.50.2

- 変更:
  - Runpod/CUDA recovery runbook を追加。
  - known-good runtime baseline を追加。
  - feature inventory / API route ownership inventory を追加。
  - runtime snapshot / route inventory export / lightweight baseline check scripts を追加。
- 壊れた時に見る場所:
  - まず `bash scripts/collect_runtime_snapshot.sh` を実行。
  - 次に `docs/runbooks/runpod_cuda_recovery.md` と `docs/runbooks/known_good_runtime_baseline.md` を見る。
  - route ownership が怪しい場合は `docs/api_route_ownership_inventory.md` と `docs/generated/route_inventory.md` を比較する。

## PR4.51

- 変更:
  - Nexus execution runtime を `app/services/nexus_execution.py` へ分離。
  - search / web search / web research / research / upload / sources / evidence / followup / ask / report build の service 境界を作成。
- 壊れた時に見る場所:
  - `app/services/nexus_execution.py`
  - service が `main.py` import や FastAPI route decorator を持っていないか
  - recursive/deep research の実行条件・response shape が変わっていないか

## PR4.52

- 変更:
  - Nexus POST/write/research/ingest route を `app/api/nexus.py` へ移動完了。
  - production `main.app` は `app.state.nexus_*_provider` 経由で既存挙動を維持。
  - `create_app()` は side-effect-free な unavailable fallback を返し、LLM / SearXNG / filesystem heavy scan / indexing / job execution を開始しない。
- 壊れた時に見る場所:
  - `app/api/nexus.py`: route / provider lookup / create_app fallback。
  - `app/services/nexus_execution.py`: Nexus 実行本体。
  - `app/nexus/router.py`: production provider の依存組み立てと、残留 route（news / market / watchlist / document delete など今回の移動対象外）。
  - `main.py` の Nexus provider registration。


## PR4.53

- 変更:
  - `KasaneCore_v2.8 == main at e94c20dfe0d23e233f4dbc817af994408e739b80` を正常復旧済み baseline として記録。
  - v2.8 時点で LLM / ASR / TTS / Nexus / Lumen 正常確認済み。
  - Runpod LLM は `-ngl=999 -> OK`, `parsed_n_gpu_layers=43`, `LLM ready`, warm-up complete を確認済み。
  - ASR OK、TTS/SBV2 OK、Nexus write/research/ingest route移動後も機能OK。
  - PR4.52 後に Nexus / Lumen / ASR / TTS / LLM が正常確認済みであることを前提に、Nexus 残骸整理と route ownership を固定。
  - moved Nexus route owner は `app/api/nexus.py`、Nexus execution body は `app/services/nexus_execution.py`。
  - `app/nexus/router.py` は provider payload helper / legacy wrapper / non-moved Nexus route（document delete/download/detail、research/source readback、news/market/watchlist、export/report subrouter）だけを残す。
- 壊れた時に見る場所:
  - `tests/test_nexus_residue_cleanup_contract.py`。
  - `docs/generated/route_inventory.md` / `.json` の duplicate path/method。
  - `app/api/nexus.py` に execution body import/call が戻っていないか。
  - `app/services/nexus_execution.py` に `APIRouter` / route decorator / `main.py` import が戻っていないか。


## PR4.55

- 変更:
  - ASR/TTS/SBV2 の safe helper / payload shaping / diagnostic shaping を `app/services/audio_runtime.py` に分離。
  - PR4.56 で low-risk audio read/status/config route を `app/api/audio.py` に移動。GET `/voice/status`、GET `/asr/config`、GET `/audio/runtime/debug`、GET `/api/tts/style-bert-vits2/models`、POST `/api/tts/style-bert-vits2/preview-normalization` の owner は `app/api/audio.py`、production payload は `main.py` provider のまま。
  - PR4.57 で POST `/tts/synthesize` の non-streaming service body は `app/services/audio_runtime.py` の `run_tts_synthesize_service_body()` に分離。ただし route owner は `main.py` のまま。
  - PR4.58 で POST `/tts/synthesize-batch` の batch service body は `app/services/audio_runtime.py` の `run_tts_synthesize_batch_service_body()` に分離。ただし route owner は `main.py` のまま。
  - PR4.59 で POST `/api/tts/style-bert-vits2/prepare` の service body は `app/services/audio_runtime.py` の `run_sbv2_prepare_service_body()` に分離。ただし route owner は `main.py` のまま。
  - TTS/SBV2 service body 抽出済み: POST `/tts/synthesize`, POST `/tts/synthesize-batch`, POST `/api/tts/style-bert-vits2/prepare`。
  - Route owner がまだ `main.py`: POST `/voice/transcribe`, POST `/voice/load`, WebSocket `/echo/stream`。`/voice/load` と `/voice/transcribe` は service body 抽出済み。
  - import-time CUDA probe 禁止は継続。
- audio runtime で壊れた時に見る順番:
  1. `main.py` route owner / production provider registration
  2. `app/services/audio_runtime.py` payload/helper shaping
  3. `app/audio/runtime_config.py` device detection
  4. Style-Bert-VITS2 runtime
  5. `scripts/collect_runtime_snapshot.sh` / `/runtime/cuda-debug` / `/audio/runtime/debug`
- 次フェーズ:
  - PR4.56: low-risk audio read/status route move.
  - PR4.57: TTS/SBV2 non-streaming service body extraction (complete; route owner unchanged).
  - PR4.58: TTS/SBV2 synthesize-batch service body extraction (complete; route owner unchanged).
  - PR4.59: SBV2 prepare service body extraction (complete; route owner unchanged).
  - PR4.60+: ASR load/transcribe棚卸しを先行し、Echo WebSocket は最後に扱う。

## Recovery invariants across all refactors

- `main.py` import 時に `detect_audio_runtime()` を呼ばない。
- `app.server` は top-level で router を大量 import しない。
- `app/server.py` の router import は `include_routers()` 内で lazy import する。
- `/voice/status` は CUDA probe しない。
- ASR/TTS/LLM CUDA probe は明示操作時だけ。
- `create_app()` fallback は CUDA / filesystem heavy scan / model load をしない。
- Nexus write/research fallback は LLM / SearXNG / filesystem heavy scan / indexing / job execution を開始しない。
- `KasaneCore_v2.8` は `e94c20dfe0d23e233f4dbc817af994408e739b80` の正常復旧済み baseline として扱う。
- moved Nexus route owner は `app/api/nexus.py`、execution body owner は `app/services/nexus_execution.py` に固定する。

## PR4.54

- 変更:
  - `KasaneCore_v2.8 == main at e94c20dfe0d23e233f4dbc817af994408e739b80` baseline 後の次対象を Echo / ASR / TTS / SBV2 audio runtime として棚卸し。
  - `docs/echo_audio_runtime_inventory.md` に WebSocket `/echo/stream`、ASR (`/voice/*`, `/asr/config`)、TTS (`/tts/synthesize`, `/tts/synthesize-batch`)、Style-Bert-VITS2 prepare / models / preview-normalization / upload、Echo session write/delete の runtime 境界を記録。
  - `app/services/audio_runtime.py` を追加。ただし route-neutral な dataclass / metadata / pure helper のみで、route 移動・実行ロジック移動・CUDA probe・ASR/TTS/SBV2 model load は行わない。
  - Echo read-only は `app/api/echo.py` に移動済み、Echo stream/write・ASR runtime・TTS/SBV2 runtime は引き続き `main.py` high-risk として固定。
- audio runtime で壊れた時に見る場所:
  - `main.py`
  - `app/audio/runtime_config.py`
  - `app/services/audio_runtime.py`
  - `app/api/echo.py`
  - `docs/echo_audio_runtime_inventory.md`
- 次フェーズ:
  - PR4.55: ASR/TTS service functions を route 移動なしで抽出。
  - PR4.56: low-risk audio status/config route を移動。
  - PR4.57: TTS/SBV2 non-streaming service body を route 移動なしで抽出。
  - PR4.58: TTS/SBV2 synthesize-batch service body を route 移動なしで抽出。
  - PR4.59: SBV2 prepare service body を route 移動なしで抽出。
  - PR4.60+: ASR load/transcribe 棚卸しを先行し、Echo WebSocket は最後に扱う。

## PR4.61 ASR transcribe seam recovery order

PR4.62 does not move `POST /voice/transcribe`; it extracts the service body to `app/services/audio_runtime.py` while leaving the route owner in `main.py`. If ASR breaks after this extraction PR, check in this order:

1. `POST /voice/load` — confirm the already-extracted ASR load service body still loads the expected model and reports device/compute type.
2. `POST /voice/transcribe` — confirm the route owner is still `main.py`, the execution body is `run_voice_transcribe_service_body(...)`, the SSE event shape is unchanged, and request normalization/base64 handling still matches `docs/asr_transcribe_runtime_inventory.md`.
3. `app/services/audio_runtime.py` — confirm PR4.62 added route-neutral `VoiceTranscribeServiceDependencies`, `VoiceTranscribeServiceResponse`, and `run_voice_transcribe_service_body(...)`; it must not import `main.py`, declare routes, or top-level import torch / ctranslate2 / faster-whisper.
4. `app/audio/runtime_config.py` — confirm effective ASR device and compute-type resolution did not regress and still avoids import-time CUDA probing.
5. faster-whisper / ctranslate2 runtime — confirm `WhisperModel` construction and `.transcribe(...)` still work with the selected model cache.
6. `/runtime/cuda-debug` — inspect CUDA availability, ctranslate2 status, and driver/runtime details.
7. `/audio/runtime/debug` — inspect audio runtime status, degraded fields, last ASR CUDA error, and related debug/status snapshots.
8. `KasaneCore_v2.8` baseline — compare against the known-good baseline if route ownership, CUDA fallback, or response shape differs.

Recovery invariants for this PR:

- CUDA fallback and cpu-int8 fallback behavior are unchanged.
- Degraded reason visibility is preserved through `_last_asr_cuda_error`, `_last_asr_cuda_error_at`, `/voice/status`, `/audio/runtime/debug`, and `/runtime/cuda-debug`.
- `POST /voice/transcribe` and WebSocket `/echo/stream` remain owned by `main.py`.


## PR4.62 ASR transcribe service body recovery notes

- POST `/voice/transcribe` route owner remains `main.py`; `AudioRuntimeHttpError` is mapped to `HTTPException` there.
- The extracted service body in `app/services/audio_runtime.py` handles validation, base64 bytes handling, SSE event shaping, transcribe invocation, and stream error events.
- `/voice/load` and `/voice/transcribe` service bodies are extracted; WebSocket `/echo/stream` remains in `main.py` and Echo extraction is last.

## PR4.63 Echo stream ASR reuse seam recovery order

If Echo stream breaks after PR4.63, inspect in this order:

1. `main.py` WebSocket `/echo/stream` route and `echo_stream_ws` websocket loop.
2. `_echo_voice_transcribe(...)` in `main.py`.
3. `app/services/audio_runtime.py` transcribe helpers for POST `/voice/transcribe` service-body reuse seams.
4. `app/services/audio_runtime.py` Echo stream seam helpers (`EchoStreamAsrInput`, `EchoStreamAsrResult`, `EchoStreamAsrDiagnostics`, `EchoStreamAsrPlan`, `build_echo_stream_asr_input(...)`, `summarize_echo_stream_asr_result(...)`, `normalize_echo_stream_asr_error(...)`).
5. `app/api/audio.py` read/status routes.
6. `/audio/runtime/debug`.
7. `/runtime/cuda-debug`.
8. `KasaneCore_v2.8` baseline.

Recovery invariants:

- WebSocket `/echo/stream` route owner and websocket execution body remain in `main.py`.
- `_echo_voice_transcribe(...)` remains the active Echo ASR call target for this PR.
- POST `/voice/load` and POST `/voice/transcribe` service bodies are extracted, but their route owners remain `main.py`.
- Echo websocket message shape, Echo session write/save/delete behavior, TTS playback chain, CUDA fallback, and debug log field names must be preserved.
