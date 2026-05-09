# PR4.38: Runtime Controls API Inventory

This inventory freezes the runtime-control and diagnostics endpoints that still
live in `main.py` after the model-settings router split and the Runpod llama,
ASR, and TTS hotfixes. This PR is documentation and contract coverage only:
no endpoint is moved, no runtime behavior is changed, and no LLM/ASR/TTS/SBV2,
Runpod llama layer search, CUDA validation/parser, UI, model DB schema, or
benchmark behavior is modified.

## Scope and owner policy

- **Current owner for all endpoints in this document:** `main.py`.
- **Already moved model-settings endpoints are out of scope:** read-only
  `GET /models/orchestration`, `GET /models/roles`, `GET /models/db`,
  `GET /models/db/status`, and `GET /model/status` are owned by
  `app/api/model_settings.py` and are tracked in
  `docs/refactor_model_settings_api_inventory.md`.
- **This PR does not move routes.** The owner contract test intentionally
  asserts that the runtime, audio, CUDA, model-manager write, and heavy model
  DB/GGUF endpoints listed here remain owned by `main.py`.
- **`create_app()` fallback meaning:** whether a future router could expose a
  conservative default provider for isolated app-factory tests without touching
  the live global/manager/service. `No` means the endpoint should not be moved
  until a real provider seam exists for its side effects or probes.

## Endpoint dependency inventory

| Category | Method / path | Current handler | Current owner | Read-only or write | Runtime side effect | Global / manager / service dependencies | `create_app()` fallback needed? | Next routerizable? | Move forbidden now? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LLM runtime controls | `GET /llm/ctx` | `get_ctx` | `main.py` | Read-only | No mutation; reports in-memory context size. | `_current_n_ctx`. | Yes; a runtime-state provider can return a safe default. | Yes, PR4.39 candidate. | No, but do not move in PR4.38. |
| LLM runtime controls | `POST /llm/ctx` | `set_ctx` | `main.py` | Write | Mutates `_current_n_ctx` after clamping. | `_current_n_ctx`. | No for write semantics without a runtime write provider. | Later only. | Yes for PR4.39/PR4.40. |
| LLM runtime controls | `GET /llm/props` | `llm_props` | `main.py` | Read-only probe | No local mutation; may call the live llama server. | `requests`, `_model_manager.llm_port`, `_current_n_ctx`. | Yes, but only via provider/fallback that avoids live HTTP in `create_app()`. | Yes, PR4.39 candidate with provider fallback. | No, but do not move in PR4.38. |
| Search runtime controls | `GET /search/status` | `search_status` | `main.py` | Read-only | No mutation. | `_search_enabled`, `_search_num_results`. | Yes; a runtime-state provider can return defaults. | Yes, PR4.39 candidate. | No, but do not move in PR4.38. |
| Search runtime controls | `POST /search/num` | `search_set_num` | `main.py` | Write | Mutates `_search_num_results`. | `_search_num_results`. | No for write semantics without a runtime write provider. | Later only. | Yes for PR4.39/PR4.40. |
| Search runtime controls | `POST /search/enable` | `search_enable` | `main.py` | Write | Mutates `_search_enabled` and prints a status line. | `_search_enabled`. | No for write semantics without a runtime write provider. | Later only. | Yes for PR4.39/PR4.40. |
| Search runtime controls | `POST /search/disable` | `search_disable` | `main.py` | Write | Mutates `_search_enabled` and prints a status line. | `_search_enabled`. | No for write semantics without a runtime write provider. | Later only. | Yes for PR4.39/PR4.40. |
| Streaming runtime controls | `GET /streaming/status` | `streaming_status` | `main.py` | Read-only | No mutation. | `_llm_streaming`. | Yes; a runtime-state provider can return defaults. | Yes, PR4.39 candidate. | No, but do not move in PR4.38. |
| Streaming runtime controls | `POST /streaming/enable` | `streaming_enable` | `main.py` | Write | Mutates `_llm_streaming` and prints a status line. | `_llm_streaming`. | No for write semantics without a runtime write provider. | Later only. | Yes for PR4.39/PR4.40. |
| Streaming runtime controls | `POST /streaming/disable` | `streaming_disable` | `main.py` | Write | Mutates `_llm_streaming` and prints a status line. | `_llm_streaming`. | No for write semantics without a runtime write provider. | Later only. | Yes for PR4.39/PR4.40. |
| Audio runtime diagnostics | `GET /audio/runtime/debug` | `audio_runtime_debug_api` | `main.py` | Read-only diagnostic probe | No intentional mutation, but probes subprocess/Python/CUDA and reads runtime state. | `detect_audio_runtime`, `_resolve_asr_runtime_config`, `voice_status`, `_tts_engine_registry`, `_probe_main_torch_cuda`, `_probe_sbv2_venv_cuda`. | Yes, but only through an audio diagnostics provider that can return conservative defaults. | PR4.40 candidate. | No, but do not move in PR4.38. |
| CUDA / model startup diagnostics | `GET /runtime/cuda-debug` | `runtime_cuda_debug` | `main.py` | Read-only diagnostic | No mutation; exposes model-manager CUDA/backend diagnostics. | `_model_manager.cuda_debug_dict()`. | Yes, through a model-manager diagnostics provider. | PR4.40 candidate. | No, but do not move in PR4.38. |
| CUDA / model startup diagnostics | `GET /debug/model-startup` | `debug_model_startup` | `main.py` | Read-only diagnostic | No mutation; reads startup hints and log tail. | `_model_manager`, `_infer_startup_failure_hints`, `LLAMA_STARTUP_LOG_PATH`, filesystem log read. | Yes, through a diagnostics provider that avoids filesystem access by default. | PR4.40 candidate. | No, but do not move in PR4.38. |
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

## Read-only runtime candidates for the next split

These endpoints are the recommended PR4.39 migration set because they are
small read-only status/control surfaces with clear provider seams:

- `GET /llm/ctx`
- `GET /llm/props`
- `GET /search/status`
- `GET /streaming/status`

A future `app/api/runtime_controls.py` should preserve production behavior by
registering providers from `main.py`, while `create_app()` should return safe
fallback values without touching live model-manager state, live HTTP probes, or
runtime globals directly.

## Diagnostics candidates after read-only runtime controls

These endpoints are the recommended PR4.40 migration set because they are
read-only but need explicit provider fallback seams for CUDA/audio/model-startup
probes:

- `GET /runtime/cuda-debug`
- `GET /audio/runtime/debug`
- `GET /debug/model-startup`

`GET /debug/llama` is intentionally not included in PR4.40 because it is a broad
heavy diagnostic that combines model catalog, GGUF metadata, VRAM/process,
health-check, and log-tail concerns.

## Deferred write/runtime actions

The following write or scheduler endpoints should stay in `main.py` until their
side-effect providers are explicit and tested:

- `POST /llm/ctx`
- `POST /search/num`
- `POST /search/enable`
- `POST /search/disable`
- `POST /streaming/enable`
- `POST /streaming/disable`
- `POST /model/switch`
- `POST /model/auto-load`

## Recommended PR sequence

1. **PR4.39: Move read-only runtime status endpoints into
   `app/api/runtime_controls.py`.** Move only `GET /llm/ctx`,
   `GET /llm/props`, `GET /search/status`, and `GET /streaming/status` behind
   runtime-state/provider fallbacks.
2. **PR4.40: Move runtime diagnostics endpoints with provider fallback.** Move
   `GET /runtime/cuda-debug`, `GET /audio/runtime/debug`, and
   `GET /debug/model-startup` after each diagnostic provider has conservative
   `create_app()` defaults.
3. **Write endpoints stay later.** Defer `POST /llm/ctx`, `POST /model/switch`,
   `POST /model/auto-load`, and search/streaming write settings until write
   providers and side-effect contracts are isolated.

## PR4.38 contract notes

- The route-owner test fixes the current owner as `main.py` for all runtime,
  audio, CUDA/model-startup diagnostic, model-manager write, and heavy
  model DB/GGUF/scan/benchmark endpoints listed in this document.
- The test also verifies that the new hotfix endpoints
  `GET /runtime/cuda-debug`, `GET /audio/runtime/debug`, and
  `GET /debug/model-startup` are present in this inventory.
- The existing model-settings router contract remains the source of truth for
  endpoints already moved out of `main.py`; PR4.38 does not retest them as
  runtime-controls migration targets.
