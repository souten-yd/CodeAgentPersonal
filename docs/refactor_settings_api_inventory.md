# PR4.25: Settings API Router Inventory

This document tracks the settings-adjacent endpoint inventory after moving the
bulk write endpoint, `POST /settings`, into `app/api/settings.py`. The bulk
write now uses the coarse `request.app.state.settings_bulk_save_provider` seam:
`main.app` installs the existing behavior through that provider, while
provider-less `create_app()` returns a conservative no-write fallback. The known
`/settings/defaults` shadowing is unchanged: `settings_get` / `settings_set` /
`settings_get_all` behavior is not changed, and no DB schema or storage location
is changed.

## Scope and important route-order finding

The primary settings endpoints are currently registered in this effective order:

1. `GET /settings-defaults` -> `app.api.settings.get_settings_defaults_api`
2. `GET /settings` -> `app.api.settings.get_settings_api`
3. `GET /settings/{key}` -> `app.api.settings.get_setting_api`
4. `PUT /settings/{key}` -> `app.api.settings.set_setting_api`
5. `POST /settings` -> `app.api.settings.save_settings_api`
6. `GET /settings/defaults` -> `main.get_settings_defaults`

Because `GET /settings/{key}` is declared before `GET /settings/defaults`, the
literal `/settings/defaults` path is currently matched by the dynamic
`/settings/{key}` route. In current behavior, `GET /settings/defaults` returns
the same shape as `GET /settings/{key}` with `key == "defaults"`, not the
`SETTINGS_DEFAULTS` dict. This PR preserves that route order and exposes
`GET /settings-defaults` as a safe unshadowed alias for callers that need the
explicit defaults map before any future route-order change. A future split can
still fix `/settings/defaults` by registering a literal defaults route before
`/{key}`, but that should be a dedicated behavior-changing PR if desired.

## Routerization recommendation summary

Recommended extraction order:

1. **Read-only canonical settings reads**: `GET /settings`, `GET /settings/{key}`.
   Completed in PR4.20 via `app/api/settings.py` with app-state providers and a
   conservative factory fallback.
2. **Unshadowed defaults alias**: `GET /settings-defaults`. Completed in
   PR4.21 via `app/api/settings.py` with a `settings_defaults_provider` and a
   conservative factory fallback. The existing `GET /settings/defaults` behavior
   is still shadowed and unchanged.
3. **Document or separately fix defaults route ordering**: `GET /settings/defaults`.
   Move this only after deciding whether to preserve the current shadowed
   behavior or intentionally expose `SETTINGS_DEFAULTS` by registering the static
   route before `/{key}`.
4. **Single-key write**: `PUT /settings/{key}`. Completed in PR4.22 via
   `app/api/settings.py` with `request.app.state.settings_set_provider`;
   factory-created apps return a conservative echo response without DB writes.
5. **Bulk write**: `POST /settings`. Provider skeleton is ready via
   `request.app.state.settings_bulk_save_provider`, but route ownership remains
   `main.save_settings_api`. The next PR should move the endpoint into the
   settings router behind that seam because it synchronizes runtime globals and
   invokes ASR/ensemble side effects.
6. **Settings-table-backed feature endpoints**: model role/orchestration and
   ensemble settings endpoints. Move after the core settings port is stable,
   because they need model catalog/resource-status providers in addition to
   settings helpers.
7. **Runtime-global settings endpoints**: `/llm/ctx`, `/search/*`, and
   `/streaming/*`. Move after deciding whether they belong in a settings router
   or a runtime-control router, because many of them do not persist changes to
   the settings table today.
8. **ASR runtime config endpoints**: `/asr/config`, `/asr/status`, `/asr/load`,
   `/asr/unload`. These read persisted ASR keys but are coupled to runtime
   process management, so they should not be part of the first settings split.

## Core settings endpoints

| Path | Method | Current handler | Response role | main.py globals/helpers used | settings helper dependency | DB write | Side effects | Can `create_app()` provide defaults? | Provider needed? | Routerization order |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/settings-defaults` | GET | `app.api.settings.get_settings_defaults_api` | Returns the explicit settings defaults map through an unshadowed alias. | `main.settings_defaults_payload` provider returns `dict(SETTINGS_DEFAULTS)`. | None directly; reads defaults through the app-state provider on `main.app`. | No. | No mutation. | Yes. `create_app()` includes the settings router and receives the same conservative fallback map used by the read-only settings route when no provider is installed. | Done: `request.app.state.settings_defaults_provider`, falling back to `default_settings_payload()`. | 2 done |
| `/settings` | GET | `app.api.settings.get_settings_api` | Returns the full effective settings map with defaults filled for unset keys. | `main.settings_get_all_payload` provider uses `settings_get_all`, `SETTINGS_DEFAULTS` indirectly, `_model_db_lock`, `_get_model_db`, `_canonicalize_settings_map` indirectly. | Direct `settings_get_all` through the app-state provider. | No. | Opens/closes model DB for reads when present; no runtime mutation. | Yes. `create_app()` includes the settings router and receives a conservative fallback map when no provider is installed. | Done: `request.app.state.settings_get_all_provider`, falling back to `default_settings_payload()`. | 1 done |
| `/settings/{key}` | GET | `app.api.settings.get_setting_api` | Returns one setting as `{key, value}` with default fallback for known keys. | `main.settings_get_payload` provider uses `settings_get`, `SETTINGS_DEFAULTS` indirectly, `_canonicalize_setting_key` indirectly, `_resolve_ctx_size` indirectly for `ctx_size`, `_model_db_lock`, `_get_model_db`. | Direct `settings_get` through the app-state provider. | No. | Opens/closes model DB for reads when present; no runtime mutation. Also currently handles `/settings/defaults` because of route shadowing. | Yes. `create_app()` includes the settings router and receives a conservative single-key fallback when no provider is installed. | Done: `request.app.state.settings_get_provider`, falling back to `default_setting_payload(key)`. | 1 done, defaults shadowing explicitly preserved |
| `/settings/{key}` | PUT | `app.api.settings.set_setting_api` | Persists one value and echoes the saved key/value through the app-state provider. | `main.settings_set_payload` provider uses `_canonicalize_setting_key`, `_resolve_ctx_size`, and `settings_set`. | Direct `settings_set` through the app-state provider on `main.app`. | Yes on `main.app`: upsert into `settings`. No in provider-less `create_app()` fallback. | Normalizes `ctx_size` before saving when the provider is installed. Does not synchronize `_current_n_ctx`, `_search_enabled`, `_llm_streaming`, ASR runtime, or ensemble JSON/guards. The factory fallback only echoes `{ok, key, value}` and intentionally does not persist. | Yes. `create_app()` includes the settings router and receives a conservative write echo when no provider is installed. | Done: `request.app.state.settings_set_provider`, falling back to `default_setting_set_payload(key, req)` with no DB write. | 4 done |
| `/settings` | POST | `app.api.settings.save_settings_api` | Bulk-save response listing saved keys. | Router uses `get_settings_bulk_save_provider`; `main.settings_bulk_save_payload` delegates to `main.save_settings_api`, which uses `_resolve_ctx_size`, `_get_summary_token_limit`, `settings_set_bulk`, `_apply_asr_runtime_settings`, `_sync_ensemble_settings_to_opencode_json`, `_apply_ensemble_execution_mode_guard`, `_search_enabled`, `_llm_streaming`, and `_current_n_ctx`. | `main.app` writes through `settings_set_bulk` inside the installed provider; provider-less `create_app()` fallback does not touch settings storage. | Yes on `main.app`: bulk upsert into `settings`. No in provider-less `create_app()` fallback. | Main-app provider preserves filtering of `max_output_tokens` and `llm_port`; normalization of `ctx_size`, `summary_max_tokens`, `read_file_inject_max_chars`, `ensemble_execution_mode`, `ensemble_auto_switch_on_low_vram`; ASR runtime config application; ensemble sync/guard; and `_search_enabled`, `_llm_streaming`, `_current_n_ctx` mutations. Factory fallback only echoes `{"ok": True, "saved": list(req.keys())}` and intentionally does not persist or mutate runtime state. | Yes for the route response shape. Full main-app behavior still requires the app-state provider. | Done: `request.app.state.settings_bulk_save_provider`, falling back to `default_settings_bulk_save_payload(req)` with no DB write. Future granular ports remain candidates: `SettingsBulkSetProvider`, `RuntimeSettingsStatePort`, `AsrRuntimeSettingsPort`, `EnsembleSettingsPort`, `SummaryTokenLimitProvider`, and `CtxSizeResolver`. | 5 done |
| `/settings/defaults` | GET | `get_settings_defaults` | Intended to return the static `SETTINGS_DEFAULTS` map. Current request behavior is shadowed by `GET /settings/{key}`. | `SETTINGS_DEFAULTS`. | None in handler; current effective request path uses `settings_get("defaults")` because of shadowing. | No. | No handler side effects. Current request opens settings DB via the dynamic route. | Yes, if registered before `/{key}` or exposed under another unshadowed path. | Optional: a defaults provider exists for the unshadowed `/settings-defaults` alias. | 3, but decide preservation vs. route-order fix in a separate PR. |

## Web-search, streaming, and LLM runtime settings endpoints

| Path | Method | Current handler | Response role | main.py globals/helpers used | settings helper dependency | DB write | Side effects | Can `create_app()` provide defaults? | Provider needed? | Routerization order |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/search/status` | GET | `search_status` | Reports in-memory web-search enabled state and result count. | `_search_enabled`, `_search_num_results`. | None. | No. | No mutation. | Yes, with a runtime-state provider. | Yes, if moved. | 6 |
| `/search/num` | POST | `search_set_num` | Sets in-memory web-search result count. | `_search_num_results`. | None. | No. | Mutates `_search_num_results`; does not persist `search_num` in settings. | No for writes without runtime-state provider. | Yes. | 6 |
| `/search/enable` | POST | `search_enable` | Enables in-memory web search. | `_search_enabled`. | None. | No. | Mutates `_search_enabled`; prints status; does not persist `search_enabled`. | No for writes without runtime-state provider. | Yes. | 6 |
| `/search/disable` | POST | `search_disable` | Disables in-memory web search. | `_search_enabled`. | None. | No. | Mutates `_search_enabled`; prints status; does not persist `search_enabled`. | No for writes without runtime-state provider. | Yes. | 6 |
| `/streaming/status` | GET | `streaming_status` | Reports in-memory LLM streaming state. | `_llm_streaming`. | None. | No. | No mutation. | Yes, with runtime-state provider. | Yes, if moved. | 6 |
| `/streaming/enable` | POST | `streaming_enable` | Enables in-memory LLM streaming. | `_llm_streaming`. | None. | No. | Mutates `_llm_streaming`; prints status; does not persist `streaming_enabled`. | No for writes without runtime-state provider. | Yes. | 6 |
| `/streaming/disable` | POST | `streaming_disable` | Disables in-memory LLM streaming. | `_llm_streaming`. | None. | No. | Mutates `_llm_streaming`; prints status; does not persist `streaming_enabled`. | No for writes without runtime-state provider. | Yes. | 6 |
| `/llm/ctx` | GET | `get_ctx` | Reports current in-memory LLM context size. | `_current_n_ctx`. | None. | No. | No mutation. | Yes, with runtime-state provider. | Yes, if moved. | 6 |
| `/llm/ctx` | POST | `set_ctx` | Sets current in-memory LLM context size. | `_current_n_ctx`. | None. | No. | Mutates `_current_n_ctx`; does not persist `ctx_size`. | No for writes without runtime-state provider. | Yes. | 6 |

## Model/ensemble settings-table-backed endpoints

| Path | Method | Current handler | Response role | main.py globals/helpers used | settings helper dependency | DB write | Side effects | Can `create_app()` provide defaults? | Provider needed? | Routerization order |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/models/roles` | GET | `get_model_role_assignments_api` | Reports role assignment options, selected model keys, and model metadata. | `get_runtime_model_catalog`, `model_db_list`, `get_runtime_task_model_map`, `_get_auto_role_model_map`, `MODEL_ROLE_OPTIONS`, `_role_setting_key`, `_resolve_ctx_size`. | Direct `settings_get` for each role key. | No. | Reads model DB/catalog; no mutation. | Not without model catalog/list providers and settings provider. | Yes: settings read provider plus model catalog/list providers. | 5 |
| `/models/roles` | POST | `save_model_role_assignments_api` | Saves explicit model assignment keys per role. | `MODEL_ROLE_OPTIONS`, `get_runtime_model_catalog`, `_role_setting_key`, `HTTPException`. | Direct `settings_set_bulk`. | Yes: bulk upsert into `settings`. | Validates requested model keys against runtime catalog. | No for writes without providers. | Yes: settings write provider plus catalog provider. | 5 |
| `/models/orchestration` | GET | `get_model_orchestration_api` | Reports orchestration feature mode, policy, quality gate, coder ladder, and model list. | `get_runtime_model_catalog`, `get_coder_ladder_keys`, `model_db_list`, `_model_text_tps`. | Direct `settings_get` for `feature_mode`, `orchestration_policy`, `quality_check_enabled`, `coder_primary`, `coder_secondary`, and `coder_tertiary`. | No. | Reads model DB/catalog; no mutation. | Not without model providers and settings provider. | Yes. | 5 |
| `/models/orchestration` | POST | `save_model_orchestration_api` | Saves orchestration policy and coder model keys. | `get_runtime_model_catalog`, `HTTPException`. | Direct `settings_set_bulk`. | Yes: bulk upsert into `settings`. | Validates feature mode, policy, and model keys. | No for writes without providers. | Yes. | 5 |
| `/ensemble/settings` | GET | `get_ensemble_settings_api` | Reports configured ensemble mode, low-VRAM auto-switch flag, and resource status. | `get_ensemble_resource_status`. | Indirect settings reads inside `get_ensemble_resource_status`. | No. | May run resource/status calculations; no direct mutation. | Not without ensemble status provider. | Yes: ensemble status provider. | 5 |
| `/ensemble/settings` | POST | `save_ensemble_settings_api` | Saves ensemble execution mode and low-VRAM behavior, then reports applied status. | `_sync_ensemble_settings_to_opencode_json`, `_apply_ensemble_execution_mode_guard`, `HTTPException`. | Direct `settings_set_bulk`; direct `settings_get` for response. | Yes: bulk upsert into `settings`. | Writes/syncs ensemble settings to `opencode.json`; may force serial mode under resource guard. | No for writes without settings and ensemble providers. | Yes. | 5 |

## ASR runtime settings endpoints

These endpoints are close to settings because `_resolve_asr_runtime_config()` and
`_apply_asr_runtime_settings()` use persisted settings keys such as `asr_engine`,
`faster_whisper_device`, and `whisper_cpp_backend`. They should be treated as
runtime-control endpoints rather than first-wave settings router candidates.

| Path | Method | Current handler | Response role | main.py globals/helpers used | settings helper dependency | DB write | Side effects | Can `create_app()` provide defaults? | Provider needed? | Routerization order |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/asr/config` | GET | `asr_config_api` | Reports resolved ASR runtime config. | `_resolve_asr_runtime_config`. | Indirect settings reads in runtime config resolution. | No. | No process mutation. | Not without ASR config provider. | Yes. | 7 |
| `/asr/status` | GET | `asr_status_api` | Reports ASR config plus whisper.cpp runtime status. | `_resolve_asr_runtime_config`, `WHISPER_CPP_SERVER_RUNTIME.status`. | Indirect settings reads. | No. | Queries runtime status. | Not without ASR runtime provider. | Yes. | 7 |
| `/asr/load` | POST | `asr_load_api` | Loads whisper.cpp runtime only when the effective engine is whisper.cpp. | `_resolve_asr_runtime_config`, `WHISPER_CPP_SERVER_RUNTIME.load`. | Indirect settings reads. | No. | May start/load ASR runtime process. | No. | Yes. | 7 |
| `/asr/unload` | POST | `asr_unload_api` | Unloads whisper.cpp runtime. | `_resolve_asr_runtime_config`, `WHISPER_CPP_SERVER_RUNTIME.unload`. | Indirect settings reads. | No. | May stop/unload ASR runtime process. | No. | Yes. | 7 |

## Notes for the future settings router split

- The settings router now owns `GET /settings-defaults`, `GET /settings`,
  `POST /settings`, `GET /settings/{key}`, and `PUT /settings/{key}` with
  app-state providers for `SETTINGS_DEFAULTS`, `settings_get_all`,
  `settings_get`, the bulk `settings_bulk_save` path, and the single-key
  `settings_set` write path.
- `PUT /settings/{key}` uses `request.app.state.settings_set_provider` on
  `main.app`; provider-less `create_app()` returns the existing echo-style
  response without saving anything to the DB.
- `main.py` still contains the bulk-save implementation used by
  `main.settings_bulk_save_payload`, but the `POST /settings` route owner is now
  `app.api.settings`; the only core settings route still registered directly in
  `main.py` is `GET /settings/defaults`.
- `POST /settings` side effects and proposed future granular provider boundaries
  are inventoried in `docs/refactor_settings_bulk_write_plan.md`.
- Preserve current `/settings/defaults` shadowed behavior in this move. If
  fixing `/settings/defaults`, do it as a separate intentional route-order PR
  with a before/after contract that makes the literal route return defaults.
- Next candidates are intentionally fixing `/settings/defaults` route order now
  that `/settings-defaults` exists as a safe reference path, or inventorying the
  model/ensemble settings endpoints for later provider splits.
- Avoid adding `create_app()` parameters just for settings in the first step.
  Prefer app state or router dependency defaults that can be overridden in tests.
- Keep runtime-global controls separate from persisted settings unless a later PR
  explicitly unifies persistence semantics.
