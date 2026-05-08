# PR4.25: Settings Bulk Write Router Move

This document inventories the `POST /settings` implementation now that the route
has moved from `main.py` into `app/api/settings.py`. The route is routerized
behind the coarse bulk-save provider because the existing main-app behavior does
more than persist settings: it also normalizes request values, applies runtime
settings, synchronizes ensemble configuration, and mutates module-level runtime
globals.

## Current owner and non-goals

- Current route owner: `app.api.settings.save_settings_api` registered as
  `POST /settings`.
- The settings router resolves `request.app.state.settings_bulk_save_provider`
  with `get_settings_bulk_save_provider(request)`.
- `main.app.state.settings_bulk_save_provider` remains installed and points at
  `main.settings_bulk_save_payload`, a thin wrapper around the unchanged
  `main.save_settings_api(req)` implementation. This preserves main-app
  filtering, normalization, `settings_set_bulk`, ASR application, ensemble
  synchronization/guarding, and runtime-global mutations.
- Provider-less `create_app()` receives a conservative router fallback that
  returns `{"ok": True, "saved": list(req.keys())}` without DB writes or runtime
  side effects.
- This PR does not change `save_settings_api`, `settings_set_bulk`, ASR runtime
  behavior, ensemble synchronization, runtime globals, route ordering, DB schema,
  or storage locations.
- The known `/settings/defaults` shadowing behavior is unchanged.

## Current processing inventory

The current `POST /settings` handler processes the incoming dictionary in this
order.

1. **Request filtering**
   - Drops `max_output_tokens` before any write.
   - Drops `llm_port` before any write.
   - The response `saved` list is based on the filtered dictionary, so filtered
     keys are not reported as saved.
2. **`ctx_size` normalization**
   - When present, passes the value through `_resolve_ctx_size(...)`.
   - Stores the resolved value back into the request dictionary as a string.
3. **`summary_max_tokens` normalization**
   - Attempts to parse an integer.
   - Allows only `200`, `400`, or `800`.
   - Replaces unsupported integer values with `_get_summary_token_limit()`.
   - Removes the key when parsing fails.
4. **`read_file_inject_max_chars` normalization**
   - Attempts to parse an integer.
   - Clamps the value to the inclusive range `4000..120000`.
   - Stores the clamped value as a string.
   - Removes the key when parsing fails.
5. **`ensemble_execution_mode` normalization**
   - Lowercases and trims the value.
   - Allows only `parallel` or `serial`.
   - Falls back to `parallel` for any other value.
6. **`ensemble_auto_switch_on_low_vram` normalization**
   - Lowercases and trims the value.
   - Stores `true` for `true`, `1`, `yes`, or `on`.
   - Stores `false` for any other value.
7. **`settings_set_bulk` write**
   - Calls `settings_set_bulk(req)` with the filtered and normalized dictionary.
   - This is the only direct persistent bulk settings write in the endpoint.
8. **`_apply_asr_runtime_settings` side effect**
   - Called with `req` when any of `asr_engine`, `faster_whisper_device`, or
     `whisper_cpp_backend` is present.
   - Applies ASR runtime configuration based on the just-saved request keys and
     existing persisted defaults/settings.
9. **`_sync_ensemble_settings_to_opencode_json` side effect**
   - Called when either `ensemble_execution_mode` or
     `ensemble_auto_switch_on_low_vram` is present.
   - Synchronizes ensemble settings to `opencode.json`.
10. **`_apply_ensemble_execution_mode_guard` side effect**
    - Called immediately after the ensemble JSON sync for the same ensemble keys.
    - May enforce the runtime execution mode guard, including low-VRAM behavior.
11. **`_search_enabled` mutation**
    - When `search_enabled` is present, mutates the module-level boolean using
      `true`, `1`, or `yes` as truthy string values.
12. **`_llm_streaming` mutation**
    - When `streaming_enabled` is present, mutates the module-level boolean using
      `true`, `1`, or `yes` as truthy string values.
13. **`_current_n_ctx` mutation**
    - When `ctx_size` is present, attempts to parse the normalized value as an
      integer and clamps it to `512..65535`.
    - Parse failures are ignored.
14. **Response shape**
    - Returns `{"ok": True, "saved": list(req.keys())}`.
    - The `saved` list reflects keys remaining after filtering and parse-failure
      removals, in the dictionary's current insertion order.

## Side-effect dependency groups

The endpoint currently crosses several boundaries that should remain separated
when it is eventually moved:

- Persistent settings storage: `settings_set_bulk`.
- Runtime settings state: `_search_enabled`, `_llm_streaming`, `_current_n_ctx`.
- Context-size resolution: `_resolve_ctx_size` and the same runtime clamp used by
  the LLM context endpoint.
- Summary token fallback: `_get_summary_token_limit`.
- ASR runtime application: `_apply_asr_runtime_settings`.
- Ensemble synchronization and guard application:
  `_sync_ensemble_settings_to_opencode_json` and
  `_apply_ensemble_execution_mode_guard`.

## Implemented router/provider seam

- **`SettingsBulkSaveProvider`**
  - Implemented in `app/api/settings.py` as
    `Callable[[dict[str, Any]], dict[str, Any]]`.
  - Looked up by `get_settings_bulk_save_provider(request)` from
    `request.app.state.settings_bulk_save_provider`.
  - Installed on `main.app` as `settings_bulk_save_payload`, which delegates to
    `save_settings_api(req)` so the current runtime behavior and response shape
    remain unchanged while the endpoint is owned by `app/api/settings.py`.
- **`default_settings_bulk_save_payload`**
  - Implemented in `app/api/settings.py` for provider-less factory apps.
  - Returns the existing bulk-save response shape without writing to the DB,
    applying ASR settings, synchronizing ensemble config, or mutating runtime
    globals.
- **Router endpoint**
  - `app.api.settings.save_settings_api` now owns `POST /settings`.
  - The endpoint delegates to the app-state provider when present and otherwise
    returns the conservative fallback payload.

## Proposed future provider boundary design

These names describe future, more granular boundaries only. Apart from the
coarse `SettingsBulkSaveProvider` skeleton above, they are not implemented in
this PR.

- **`SettingsBulkSetProvider`**
  - Accepts the final filtered/normalized request dictionary.
  - Owns the persistent `settings_set_bulk` call.
  - Should be injectable through app state when `POST /settings` moves to the
    settings router, with a provider-less factory fallback that avoids DB writes
    if behavior parity permits a safe echo path.
- **`RuntimeSettingsStatePort`**
  - Owns in-memory mutations for search enabled, LLM streaming enabled, and
    current context size.
  - Makes the module globals explicit instead of importing them into the router.
- **`AsrRuntimeSettingsPort`**
  - Owns the conditional ASR runtime apply call.
  - Should receive the saved request dictionary and decide whether/how to apply
    ASR settings without coupling the router to ASR internals.
- **`EnsembleSettingsPort`**
  - Owns ensemble JSON synchronization and execution-mode guard application.
  - Should expose a single high-level method for applying the ensemble side
    effects after relevant keys are saved.
- **`SummaryTokenLimitProvider`**
  - Owns fallback resolution for unsupported `summary_max_tokens` values.
  - Keeps DB-backed/default summary token policy out of the router.
- **`CtxSizeResolver`**
  - Owns `ctx_size` normalization before persistence.
  - Should be shared with the single-key write provider to avoid divergent
    context-size behavior.

## Suggested next work

Future work should service-ize the bulk save payload and split the coarse
provider into more granular ports when that reduces coupling: persistent bulk
settings writes, runtime global state, ASR runtime application, ensemble sync and
guard application, summary-token fallback, and context-size resolution. A
separate PR may also address the `/settings/defaults` route-order issue if the
intended behavior is to expose `SETTINGS_DEFAULTS` at that literal path.
