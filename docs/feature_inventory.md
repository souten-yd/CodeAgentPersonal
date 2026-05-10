# KasaneCore Feature Inventory

この一覧は「何があるか」「壊れた時にどの領域を見るか」を素早く把握するための機能 inventory です。PR4.50.2 では機能分割を進めず、復旧・切り分け用の文書化だけを行います。

## Lumen

- 通常チャット。
- LLM endpoint: `http://127.0.0.1:8080/v1/chat/completions`。
- 関連 API:
  - `POST /chat`
  - `POST /stream`
  - `POST /task`
  - `POST /task/stream`
  - `POST /jobs/submit`
  - `GET /jobs/{job_id}`
  - `GET /jobs/{job_id}/poll`
  - `GET /jobs/{job_id}/stream`
  - `GET /projects/{project}/jobs`
- 関連データ:
  - jobs submit / poll / history
  - chat history
  - LLM telemetry / ctx / props

## Atlas

- Agent / workflow / autonomous execution。
- Task planning / guided workflow / patch chain / review / requirement handling。
- 現状の owner:
  - 多くは `main.py` に残る。
  - 一部 service / planner / tests は分離済み。
- 未分離部分:
  - `/api/atlas/*`
  - `/api/plans/*`
  - `/api/runs/*`
  - `/agent/*`
- 壊れた時の見方:
  - LLM 呼び出しなのか、workflow state なのか、UI contract なのかを分ける。
  - runtime CUDA 問題と Atlas workflow 問題を混ぜない。

## Nexus

- summary。
- documents。
- active jobs。
- web status。
- research / deep research / recursive research。
- ingest / index / report。
- owner:
  - read-only dashboard endpoints: `app/api/nexus.py`
  - execution / research services: `app/nexus/*`, `app/services/nexus_execution.py`, and remaining `main.py` routes where applicable
- 壊れた時の見方:
  - read-only endpoint なら `app/api/nexus.py` と provider registration を確認する。
  - research execution なら `app/nexus/research_api.py`, `app/nexus/research_agent.py`, `app/services/nexus_execution.py` を確認する。

## Echo

- save-status。
- sessions。
- echo stream。
- ASR。
- TTS / SBV2。
- owner:
  - read-only `save-status` / `sessions`: `app/api/echo.py`
  - WebSocket `/echo/stream`: `main.py`
  - ASR / TTS runtime routes: `main.py`, `app/asr/*`, `app/tts/*`
- 壊れた時の見方:
  - sessions/save-status は read-only provider 問題として見る。
  - `/echo/stream`, `/voice/transcribe`, `/tts/synthesize` は high-risk audio runtime として見る。

## Models

- model DB。
- auto-load。
- llama-server。
- Runpod Linux `-ngl` 探索。
- Windows auto-fit。
- owner:
  - read-only DB/status: `app/api/model_settings.py`
  - auto-load / llama-server process / ModelManager runtime: `main.py`
- 壊れた時の見方:
  - Model DB の read-only endpoint と、llama-server 起動・GPU offload 探索を分ける。
  - Runpod Linux では `Runpod/Linux explicit search start high=999` と `final -ngl=999 parsed_n_gpu_layers=43` を確認する。

## Runtime

- system summary。
- CUDA debug。
- audio runtime debug。
- runtime controls。
- search / streaming controls。
- owner:
  - lightweight controls and diagnostics: `app/api/runtime_controls.py`, `app/api/system_status.py`, `app/api/system.py`
  - production provider wiring: `main.py`
- 壊れた時の見方:
  - `create_app()` fallback は heavy CUDA / filesystem / model load をしないことを確認する。
  - production provider だけが live runtime に触ることを確認する。

## Recovery tooling

- `docs/runbooks/runpod_cuda_recovery.md`: 障害時に最初に読む runbook。
- `docs/runbooks/known_good_runtime_baseline.md`: 正常時 baseline。
- `scripts/collect_runtime_snapshot.sh`: 診断情報一括取得。
- `scripts/check_runtime_baseline.py`: lightweight endpoint baseline check。
- `scripts/export_route_inventory.py`: FastAPI route inventory export。

## PR4.68 Lumen chat-only jobs

- `POST /jobs/submit` is the Lumen chat submit endpoint: normal chat plus optional lightweight Web assist.
- Legacy task mode is removed from Lumen; `task`, `agent_task`, and `legacy_task` submit modes fail before job creation.
- Lumen Web assist is controlled by `search_policy` (`off` / `auto` / `on`) and a clamped `LumenSearchBudget`.
- Nexus remains responsible for Deep Research, Recursive Research, report generation, and knowledge accumulation.
- Atlas / Agent remains responsible for autonomous execution, file edits, code execution, and multi-step pipelines.
