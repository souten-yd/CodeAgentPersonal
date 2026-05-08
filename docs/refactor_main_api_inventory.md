# main.py API split inventory: system endpoints

This memo records the `main.py` split status for system endpoints after moving
`/system/summary`. The goal is to preserve `uvicorn main:app` compatibility and
the current response bodies while identifying which higher-coupling endpoints
still need provider/service design before they can move.

## Current split baseline

- `app.server.create_app()` includes `app.api.system.router` together with the
  health router. The factory is intentionally minimal and does not yet mirror
  all of `main.app`.
- `app/api/system.py` currently owns `GET /system/readiness`,
  `GET /system/env`, `GET /system/usage`, `GET /system/usage/debug`, and
  `GET /system/summary`. Provider-backed routes support app-state hooks so
  `main.app` can keep its `main.py` probes while `create_app()` returns stable
  default payloads.
- `main.py` still assigns `app.state.system_readiness_provider` to the richer
  `system_readiness_payload()` implementation.
- `GET /system/env` has moved to `app/api/system.py` and is now served by
  both `create_app()` and `main.app` through `include_routers(app)` without a
  provider hook.
- `GET /system/usage` has moved to the router handler in `app/api/system.py`.
  Provider-less factory apps return the default unavailable payload; `main.app`
  preserves existing behavior through `app.state.system_usage_provider =
  get_system_usage_info`.
- `GET /system/summary` has moved to the router handler in `app/api/system.py`.
  Provider-less factory apps return a conservative default summary payload;
  `main.app` preserves the previous summary body through
  `app.state.system_summary_provider = system_summary_payload`.

## Endpoint inventory

| Endpoint | Handler in `main.py` | Response role | Main globals / helpers used | Side effects | Available from `create_app()` today? | Provider needed? | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /system/readiness` | router handler in `app/api/system.py`; `main.py` provider is `system_readiness_payload()` | Low-cost readiness shape and optional model DB / LLM autoload probes | `model_db_exists()`, `model_db_status_summary()`, `_should_startup_autoload_llm()`, `_model_health_ok()`, `_model_manager.llm_port` via provider | No writes expected; performs probes | Yes | Already providerized | Baseline split endpoint. |
| `GET /system/env` | router handler in `app/api/system.py` | Runtime environment profile: Runpod, OS, GPU, Style-Bert-VITS2 device env var | `os.environ`, `detect_runpod()`, `detect_os_profile()`, `detect_gpu_profile()` inside `app/api/system.py` | No writes expected; catches detector failures and returns fallback body | Yes | No provider required | Moved to `app/api/system.py`; `main.app` receives it through `include_routers(app)` with no duplicate inline route in `main.py`. |
| `GET /system/usage` | router handler in `app/api/system.py`; `main.py` provider is `get_system_usage_info` via `app.state.system_usage_provider` | CPU/RAM/GPU usage snapshot | Provider hook calls `get_system_usage_info()`, which uses `psutil` when available, OS fallback probes, `_select_working_gpu_backend()`, `_probe_gpu_static()`, `settings_get()`, `settings_set()`, and `_set_last_usage_diag()` | Writes runtime diagnostics to `_last_usage_diag`; may persist `gpu_usage_backend` selection to settings when auto-detecting a backend | Yes; default unavailable payload without provider | Yes; `main.app` uses `app.state.system_usage_provider` | Moved to `app/api/system.py`. Factory apps without a provider intentionally return the conservative unavailable payload. |
| `GET /system/usage/debug` | router handler in `app/api/system.py`; `main.py` provider is `system_usage_debug_payload()` via `app.state.system_usage_debug_provider` | Debug view for the last usage probe plus a fresh final usage snapshot | Provider hook calls `system_usage_debug_payload()`, which calls `get_system_usage_info()` before `_get_last_usage_diag()` | Same side effects as `/system/usage` because the provider calls `get_system_usage_info()`; also reads `_last_usage_diag` | Yes; default unavailable debug payload without provider | Yes; `main.app` uses `app.state.system_usage_debug_provider` | Moved to `app/api/system.py`. Factory apps without a provider intentionally return the conservative unavailable debug payload. |
| `GET /system/summary` | router handler in `app/api/system.py`; `main.py` provider is `system_summary_payload()` via `app.state.system_summary_provider` | Combined health, model status, and usage summary | Provider hook calls `system_summary_payload()`, which uses `_model_manager.status_dict()`, `get_system_usage_info()`, and `_get_lightweight_health_status()` | Same usage side effects as `/system/usage`; network probe to localhost LLM health; optional Docker CLI probe | Yes; default conservative summary payload without provider | Yes; `main.app` uses `app.state.system_summary_provider` | Moved to `app/api/system.py`. Factory apps without a provider intentionally return unavailable/empty summary fields with the existing major key shape. |
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

`GET /system/env`, `GET /system/usage`, `GET /system/usage/debug`, and
`GET /system/summary` have now moved to `app/api/system.py`. `/system/usage`
uses the app-state provider hook; `main.app` sets
`app.state.system_usage_provider = get_system_usage_info` to preserve the
existing runtime behavior. `/system/usage/debug` uses
`app.state.system_usage_debug_provider`, and `main.app` sets that provider to
`system_usage_debug_payload()` to preserve the existing debug payload sequence.
`/system/summary` now uses `app.state.system_summary_provider`, and `main.app`
sets that provider to `system_summary_payload()` so model-manager, usage, and
lightweight-health logic remain in `main.py`. `create_app()` has no summary
provider, so it returns the router's conservative unavailable/empty default
payload.

Next candidate:

- Prepare a settings router inventory/migration for `/settings*`. These routes
  are not system status endpoints and include writes/route-order compatibility
  concerns, so they should move separately.
