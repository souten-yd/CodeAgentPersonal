# main.py API split inventory: system endpoints

This memo records the next `main.py` split candidates after `/system/readiness`.
It intentionally does **not** move endpoint bodies. The goal is to identify the
lowest-risk endpoint that can be moved next into `app/api/system.py` while
preserving `uvicorn main:app` compatibility and the current response bodies.

## Current split baseline

- `app.server.create_app()` includes `app.api.system.router` together with the
  health router. The factory is intentionally minimal and does not yet mirror
  all of `main.app`.
- `app/api/system.py` currently owns only `GET /system/readiness`. It supports a
  `request.app.state.system_readiness_provider` hook so `main.app` can keep its
  `main.py` probes while `create_app()` returns a stable default payload.
- `main.py` still assigns `app.state.system_readiness_provider` to the richer
  `system_readiness_payload()` implementation.

## Endpoint inventory

| Endpoint | Handler in `main.py` | Response role | Main globals / helpers used | Side effects | Available from `create_app()` today? | Provider needed? | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /system/readiness` | router handler in `app/api/system.py`; `main.py` provider is `system_readiness_payload()` | Low-cost readiness shape and optional model DB / LLM autoload probes | `model_db_exists()`, `model_db_status_summary()`, `_should_startup_autoload_llm()`, `_model_health_ok()`, `_model_manager.llm_port` via provider | No writes expected; performs probes | Yes | Already providerized | Baseline split endpoint. |
| `GET /system/env` | `system_env()` | Runtime environment profile: Runpod, OS, GPU, Style-Bert-VITS2 device env var | `os.environ`, `detect_runpod()`, `detect_os_profile()`, `detect_gpu_profile()` | No writes expected; catches detector failures and returns fallback body | No | No provider required for the current implementation | Best next move candidate: dependencies already live outside `main.py` except `os`, response body is self-contained, and it does not depend on model manager, settings DB, middleware, lifespan, workspace paths, or UI assets. |
| `GET /system/usage` | `system_usage_api()` | CPU/RAM/GPU usage snapshot | `get_system_usage_info()`, which uses `psutil` when available, OS fallback probes, `_select_working_gpu_backend()`, `_probe_gpu_static()`, `settings_get()`, `settings_set()`, and `_set_last_usage_diag()` | Writes runtime diagnostics to `_last_usage_diag`; may persist `gpu_usage_backend` selection to settings when auto-detecting a backend | No | Yes, unless usage collection is first extracted into a service module with explicit settings/diag dependencies | Useful endpoint, but not the safest next move because the implementation currently couples status collection to settings persistence and diagnostic globals. |
| `GET /system/usage/debug` | `system_usage_debug_api()` | Debug view for the last usage probe plus a fresh final usage snapshot | `get_system_usage_info()`, `_get_last_usage_diag()` | Same side effects as `/system/usage` because it calls `get_system_usage_info()`; also reads `_last_usage_diag` | No | Yes, or move together with a usage provider/service | Should move after `/system/usage`, not before it. |
| `GET /system/summary` | `system_summary()` | Combined health, model status, and usage summary | `_model_manager.status_dict()`, `get_system_usage_info()`, `_get_lightweight_health_status()` | Same usage side effects as `/system/usage`; network probe to localhost LLM health; optional Docker CLI probe | No | Yes | Higher coupling: model manager state, usage collection, requests, Docker availability, and sandbox container constants. |
| `GET /settings` | `get_settings_api()` | Full settings state; adjacent to system/runtime state because it exposes GPU/model/runtime configuration | `settings_get_all()`, `SETTINGS_DEFAULTS`, model DB lock/connection helpers | Read-only for GET | No | Yes, if moved into a router without moving settings storage | Keep out of `app/api/system.py` for now; better suited to a future settings router. |
| `GET /settings/{key}` | `get_setting_api()` | Single setting lookup | `settings_get()` and related canonicalization/default helpers | Read-only for GET | No | Yes, if moved into a settings router | Route order currently places this before `/settings/defaults`, so `/settings/defaults` is handled as key `defaults`. Do not change route order in this inventory PR because it would alter behavior. |
| `PUT /settings/{key}` | `set_setting_api()` | Single setting write | `settings_set()`, `_canonicalize_setting_key()`, `_resolve_ctx_size()` | Writes settings DB | No | Yes, if moved into a settings router | Not a system-router candidate. |
| `GET /settings/defaults` | `get_settings_defaults()` | Intended settings defaults response | `SETTINGS_DEFAULTS` | Read-only | No | Yes, if route-order behavior is intentionally corrected later | Currently shadowed by `/settings/{key}` in `main.app`; inventory only. |

## Debug/runtime-adjacent endpoints intentionally excluded

These endpoints are runtime diagnostics, but they are not safe system-router
moves in the next step because they are tied to model, TTS, or debug harness
concerns that are out of scope for this phase:

- `GET /debug/model-startup`: model manager internals and llama startup log.
- `GET /debug/llama`: llama process/model debug details.
- `GET /debug/echo`: Echo/ASR/TTS-adjacent debug surface.
- `GET /debug/TTS`: TTS debug surface.
- `GET /debug/tests` and debug test run routes: debug harness UI/API state.

## Recommendation

Move `GET /system/env` next.

Rationale:

1. It is the only remaining `/system/*` endpoint whose handler body is
   effectively self-contained and read-only.
2. Its dependencies are already in `app.env_detection`, plus `os.environ`; no
   model/TTS/ASR/Nexus/Atlas/Echo imports or app-factory argument changes are
   required.
3. It can be provided by `create_app()` directly from `app/api/system.py` without
   a provider hook, because it does not need `main.py` globals.
4. It already has an internal fallback body for detector exceptions, reducing
   the risk of introducing new 500s during the move.

Defer these endpoints:

- Defer `/system/usage` and `/system/usage/debug` until usage collection is
  extracted behind a provider/service boundary, because backend auto-selection
  can write settings and debug state.
- Defer `/system/summary` until model-manager and lightweight-health probes can
  be injected or separately modularized.
- Defer `/settings*` to a dedicated settings-router inventory/migration because
  these routes are not system status endpoints and include writes/route-order
  compatibility concerns.
