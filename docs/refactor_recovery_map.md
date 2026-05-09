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

## Recovery invariants across all refactors

- `main.py` import 時に `detect_audio_runtime()` を呼ばない。
- `app.server` は top-level で router を大量 import しない。
- `app/server.py` の router import は `include_routers()` 内で lazy import する。
- `/voice/status` は CUDA probe しない。
- ASR/TTS/LLM CUDA probe は明示操作時だけ。
- `create_app()` fallback は CUDA / filesystem heavy scan / model load をしない。
