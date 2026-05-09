# PR4.48: Runtime Controls API Inventory

This inventory tracks the runtime-control and diagnostics endpoints after the
low-risk read-only runtime status split, the lower-risk read-only diagnostics
split, the lightweight runtime write-control split, and the Runpod llama, ASR,
and TTS hotfixes. PR4.39 moved only the read-only runtime status endpoints into
`app/api/runtime_controls.py`; PR4.40 then moved the selected read-only
diagnostics with provider fallbacks. PR4.48 moved only lightweight runtime
write/control endpoints into the same router behind provider fallbacks. No
heavy, LLM inference, ASR/TTS/SBV2 runtime execution, Runpod llama layer search,
CUDA validation/parser, UI, model DB schema, job execution, WebSocket execution,
or benchmark behavior is modified.

## Scope and owner policy

- **Current owner for read-only runtime status, selected diagnostic endpoints, and lightweight runtime write controls:** `app/api/runtime_controls.py`.
- **Current owner for model lifecycle writes, execution endpoints, broad heavy diagnostic, and heavy endpoints in this document:** `main.py`.
- **Already moved model-settings endpoints are out of scope:** read-only
  `GET /models/orchestration`, `GET /models/roles`, `GET /models/db`,
  `GET /models/db/status`, and `GET /model/status` are owned by
  `app/api/model_settings.py` and are tracked in
  `docs/refactor_model_settings_api_inventory.md`.
- **PR4.39 moved only the read-only runtime status endpoints.** The owner
  contract test preserves that status split and PR4.40 extends runtime-controls
  ownership to the selected CUDA/audio/model-startup diagnostics. PR4.48 moves
  only lightweight runtime write/control endpoints to the router. `GET
  /debug/llama`, model-manager write, job execution, ASR/TTS execution, Echo
  WebSocket execution, Nexus write/research/ingest, and heavy model DB/GGUF
  endpoints listed here remain owned by `main.py` or their existing routers.
- **`create_app()` fallback meaning:** whether a future router could expose a
  conservative default provider for isolated app-factory tests without touching
  the live global/manager/service. `No` means the endpoint should not be moved
  until a real provider seam exists for its side effects or probes.

## Endpoint dependency inventory

| Category | Method / path | Current handler | Current owner | Read-only or write | Runtime side effect | Global / manager / service dependencies | `create_app()` fallback needed? | Next routerizable? | Move forbidden now? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LLM runtime controls | `GET /llm/ctx` | `get_runtime_llm_ctx_api` | `app/api/runtime_controls.py` | Read-only | No mutation; reports in-memory context size. | `app.state.runtime_llm_ctx_provider` in production; safe fallback in `create_app()`. | Implemented; returns safe defaults without runtime access. | Moved in PR4.39. | No. |
| LLM runtime controls | `POST /llm/ctx` | `set_runtime_llm_ctx_api` | `app/api/runtime_controls.py` | Lightweight write | Production provider mutates `_current_n_ctx` after clamping; `create_app()` fallback only echoes `n_ctx`. | `app.state.runtime_llm_ctx_set_provider` in production. | Implemented; fallback avoids llama-server, model manager, DB, and runtime globals. | Moved in PR4.48. | No. |
| LLM runtime controls | `GET /llm/props` | `get_runtime_llm_props_api` | `app/api/runtime_controls.py` | Read-only probe | No local mutation; production provider preserves the existing live llama-server probe/fallback behavior. | `app.state.runtime_llm_props_provider` in production; safe fallback in `create_app()`. | Implemented; fallback avoids live HTTP. | Moved in PR4.39. | No. |
| Search runtime controls | `GET /search/status` | `get_search_status_api` | `app/api/runtime_controls.py` | Read-only | No mutation. | `app.state.search_status_provider` in production; safe fallback in `create_app()`. | Implemented; returns search disabled/default result count. | Moved in PR4.39. | No. |
| Search runtime controls | `POST /search/num` | `set_search_num_api` | `app/api/runtime_controls.py` | Lightweight write | Production provider mutates `_search_num_results`; `create_app()` fallback only echoes `num_results`. | `app.state.search_num_provider` in production. | Implemented; fallback avoids search process management and runtime globals. | Moved in PR4.48. | No. |
| Search runtime controls | `POST /search/enable` | `enable_search_api` | `app/api/runtime_controls.py` | Lightweight write | Production provider mutates `_search_enabled` and prints a status line; fallback only returns the existing response shape. | `app.state.search_enable_provider` in production. | Implemented; fallback avoids SearXNG process management and runtime globals. | Moved in PR4.48. | No. |
| Search runtime controls | `POST /search/disable` | `disable_search_api` | `app/api/runtime_controls.py` | Lightweight write | Production provider mutates `_search_enabled` and prints a status line; fallback only returns the existing response shape. | `app.state.search_disable_provider` in production. | Implemented; fallback avoids SearXNG process management and runtime globals. | Moved in PR4.48. | No. |
| Streaming runtime controls | `GET /streaming/status` | `get_streaming_status_api` | `app/api/runtime_controls.py` | Read-only | No mutation. | `app.state.streaming_status_provider` in production; safe fallback in `create_app()`. | Implemented; returns streaming disabled by default. | Moved in PR4.39. | No. |
| Streaming runtime controls | `POST /streaming/enable` | `enable_streaming_api` | `app/api/runtime_controls.py` | Lightweight write | Production provider mutates `_llm_streaming` and prints a status line; fallback only returns the existing response shape. | `app.state.streaming_enable_provider` in production. | Implemented; fallback avoids LLM calls and runtime globals. | Moved in PR4.48. | No. |
| Streaming runtime controls | `POST /streaming/disable` | `disable_streaming_api` | `app/api/runtime_controls.py` | Lightweight write | Production provider mutates `_llm_streaming` and prints a status line; fallback only returns the existing response shape. | `app.state.streaming_disable_provider` in production. | Implemented; fallback avoids LLM calls and runtime globals. | Moved in PR4.48. | No. |
| Audio runtime diagnostics | `GET /audio/runtime/debug` | `get_audio_runtime_debug_api` | `app/api/runtime_controls.py` | Read-only diagnostic probe | No intentional mutation; production provider preserves existing subprocess/Python/CUDA probes and runtime-state reads. | `app.state.audio_runtime_debug_provider` in production; safe fallback in `create_app()`. | Implemented; fallback avoids live audio/CUDA/subprocess probes. | Moved in PR4.40. | No. |
| CUDA / model startup diagnostics | `GET /runtime/cuda-debug` | `get_runtime_cuda_debug_api` | `app/api/runtime_controls.py` | Read-only diagnostic | No mutation; production provider exposes existing model-manager CUDA/backend diagnostics. | `app.state.runtime_cuda_debug_provider` in production; safe fallback in `create_app()`. | Implemented; fallback avoids model-manager/GPU access. | Moved in PR4.40. | No. |
| CUDA / model startup diagnostics | `GET /debug/model-startup` | `get_model_startup_debug_api` | `app/api/runtime_controls.py` | Read-only diagnostic | No mutation; production provider preserves existing startup hints and log-tail reads. | `app.state.model_startup_debug_provider` in production; safe fallback in `create_app()`. | Implemented; fallback avoids model-manager and filesystem access. | Moved in PR4.40. | No. |
| CUDA / model startup diagnostics | `GET /debug/llama` | `debug_llama` | `main.py` | Read-only heavy diagnostic | No intentional mutation; performs broad model, VRAM, process, health, and log probes. | `_model_manager`, `_get_total_free_vram_mb`, `_calc_safe_gpu_layers`, `_read_gguf_metadata`, runtime health/log helpers. | No until the broad debug payload is split into providers. | Not yet. | Yes; leave in `main.py`. |
| Model manager write/runtime controls | `POST /model/switch` | `model_switch` | `main.py` | Write/runtime action | Starts a background thread that calls `_model_manager.ensure_model(key)`. | `_model_manager`, `choose_model_for_role`, `get_runtime_model_catalog`, `threading`. | No for write/thread semantics without a model-manager action provider. | Later only. | Yes for PR4.39/PR4.40. |
| Model manager write/runtime controls | `POST /model/auto-load` | `model_auto_load` | `main.py` | Write/runtime action | Schedules default model load and may start background work. | `schedule_default_model_load`. | No for scheduler semantics without a provider. | Later only. | Yes for PR4.39/PR4.40. |
| Heavy model DB / GGUF / scan / benchmark | `GET /models/hardware` | `model_hardware_api` | `main.py` | Read-only heavy probe | No mutation, but probes system hardware. | `get_system_hardware_info`. | Yes only with a hardware provider. | Not in runtime-controls split. | Yes; leave in `main.py`. |
| Heavy model DB / GGUF / scan / benchmark | `GET /models/gguf/search` | `search_gguf_models_api` | `main.py` | Read-only external query | No local mutation, but calls Hugging Face and checks local hardware/disk. | `requests`, `get_system_hardware_info`, settings/root-folder helpers, disk and GGUF helpers. | No until external-query provider exists. | Not in runtime-controls split. | Yes; leave in `main.py`. |
| Heavy model DB / GGUF / scan / benchmark | `POST /models/gguf/download` | `download_gguf_api` | `main.py` | Write/background action | Starts or coordinates GGUF download state and filesystem writes. | Download status globals, Hugging Face/download helpers, filesystem/settings helpers. | No. | Not in runtime-controls split. | Yes; leave in `main.py`. |
| Heavy model DB / GGUF / scan / benchmark | `GET /models/gguf/download/status` | `gguf_download_status_api` | `main.py` | Read-only status | No mutation; reads download status global. | GGUF download status global/lock. | Yes only with a download-status provider. | Not in runtime-controls split. | Yes; leave in `main.py`. |
| Heavy model DB / GGUF / scan / benchmark | `POST /models/db/scan` | `scan_model_folder_api` | `main.py` | Write/background action | Starts scan work and can populate/update model DB entries. | Model DB helpers, scan status globals/threading, filesystem/settings helpers. | No. | Not in runtime-controls split. | Yes; leave in `main.py`. |
| Heavy model DB / GGUF / scan / benchmark | `GET /models/db/scan/status` | `model_scan_status_api` | `main.py` | Read-only status | No mutation; reads scan status global. | Model scan status global/lock. | Yes only with a scan-status provider. | Not in runtime-controls split. | Yes; leave in `main.py`. |
| Heavy model DB / GGUF / scan / benchmark | `POST /models/db/benchmark/{mid}` | `benchmark_model_api` | `main.py` | Write/heavy action | Runs or schedules benchmark work and updates benchmark metadata. | Model DB helpers, benchmark runner, model/runtime/hardware helpers. | No. | Not in runtime-controls split. | Yes; leave in `main.py`. |
| Heavy model DB / GGUF / scan / benchmark | `POST /models/db/toggle/{mid}` | `toggle_model_enabled` | `main.py` | Write | Updates model enabled state. | `model_db_update` and model DB helpers. | No. | Not in runtime-controls split. | Yes; leave in `main.py`. |
| Heavy model DB / GGUF / scan / benchmark | `POST /models/db/toggle_vlm/{mid}` | `toggle_model_vlm_enabled` | `main.py` | Write | Updates model VLM flag. | `model_db_update` and model DB helpers. | No. | Not in runtime-controls split. | Yes; leave in `main.py`. |

## Read-only runtime endpoints moved in PR4.39

These endpoints moved in PR4.39 because they are small read-only status/control
surfaces with clear provider seams:

- `GET /llm/ctx`
- `GET /llm/props`
- `GET /search/status`
- `GET /streaming/status`

`app/api/runtime_controls.py` preserves production behavior by reading provider
payloads registered from `main.py`, while `create_app()` returns safe fallback
values without touching live model-manager state, live HTTP probes, or runtime
globals directly.

## Read-only diagnostics moved in PR4.40

PR4.40 moved the lower-risk read-only diagnostic endpoints into
`app/api/runtime_controls.py` behind explicit provider seams. Production
`main.app` registers providers that preserve the existing CUDA/audio/model-startup
payload shapes, while `create_app()` returns conservative fallbacks without live
CUDA, audio, model-manager, subprocess, or log probes:

- `GET /runtime/cuda-debug`
- `GET /audio/runtime/debug`
- `GET /debug/model-startup`

`GET /debug/llama` remains in `main.py` because it is a broad heavy diagnostic
that combines model catalog, GGUF metadata, VRAM/process, health-check, and
log-tail concerns.

## Lightweight write controls moved in PR4.48

PR4.48 moved only lightweight runtime write/control endpoints into
`app/api/runtime_controls.py` behind explicit provider seams. Production
`main.app` registers providers that preserve the existing response shapes and
state-saving behavior, while `create_app()` returns side-effect-free fallback
payloads without touching llama-server, the model manager, LLM HTTP endpoints,
SearXNG process management, ASR/TTS, filesystem scans, or job execution:

- `POST /llm/ctx`
- `POST /search/num`
- `POST /search/enable`
- `POST /search/disable`
- `POST /streaming/enable`
- `POST /streaming/disable`

## Deferred execution/heavy runtime actions

The following execution, lifecycle, scheduler, and heavy endpoints stay in
`main.py` until their side-effect providers are explicit and tested:

- `POST /model/switch`
- `POST /model/auto-load`
- `POST /jobs/submit`
- `POST /voice/transcribe`
- `POST /tts/synthesize`
- `POST /tts/synthesize-batch`
- `WebSocket /echo/stream`
- Nexus research, ingest, upload, delete, source, and other write routes

## Recommended PR sequence

1. **PR4.39: Move read-only runtime status endpoints into
   `app/api/runtime_controls.py`.** Move only `GET /llm/ctx`,
   `GET /llm/props`, `GET /search/status`, and `GET /streaming/status` behind
   runtime-state/provider fallbacks.
2. **PR4.40: Move runtime diagnostics endpoints with provider fallback.** Move
   `GET /runtime/cuda-debug`, `GET /audio/runtime/debug`, and
   `GET /debug/model-startup` after each diagnostic provider has conservative
   `create_app()` defaults. Keep `GET /debug/llama` in `main.py` as a broad
   heavy diagnostic.
3. **PR4.48: Move lightweight runtime write controls.** Move only `POST
   /llm/ctx`, `POST /search/num`, `POST /search/enable`, `POST
   /search/disable`, `POST /streaming/enable`, and `POST /streaming/disable`
   after write providers and side-effect-free fallbacks are isolated.
4. **Execution and lifecycle endpoints stay later.** Defer `POST
   /model/switch`, `POST /model/auto-load`, `POST /jobs/submit`, ASR/TTS
   execution, Echo WebSocket execution, Nexus write/research/ingest, and heavy
   model DB/GGUF operations to dedicated plans.

## PR4.39 / PR4.40 / PR4.48 contract notes

- The route-owner test fixes `app/api/runtime_controls.py` as the owner for
  `GET /llm/ctx`, `GET /llm/props`, `GET /search/status`, and
  `GET /streaming/status`.
- PR4.40 extends that owner contract to `GET /runtime/cuda-debug`,
  `GET /audio/runtime/debug`, and `GET /debug/model-startup`.
- PR4.48 extends that owner contract to lightweight runtime write controls:
  `POST /llm/ctx`, `POST /search/num`, `POST /search/enable`, `POST
  /search/disable`, `POST /streaming/enable`, and `POST /streaming/disable`.
- The same test fixes `main.py` as the owner for `GET /debug/llama`,
  model-manager write/lifecycle, job execution, ASR/TTS execution, Echo
  WebSocket execution, and heavy model DB/GGUF/scan/benchmark endpoints listed
  in this document.
- The existing model-settings router contract remains the source of truth for
  endpoints already moved out of `main.py`.
