# UI Module Ownership

## Scope
KasaneCore UI uses root `ui.html` plus external scripts under `web/js/`.
This document defines ownership after PR-UI-1 through PR-UI-12.

## Root UI
- `ui.html`
  - Owns static DOM skeleton
  - Owns compatibility inline handlers
  - Owns high-level event wiring not yet moved
  - Must not duplicate module-owned API/state/rendering helpers unless kept as compatibility shim

## Atlas modules
### `web/js/atlas_api.js`
Owns:
- Atlas HTTP API wrappers
- `window.AtlasAPI`
- `__kasaneModules.atlasApi`

Must not own:
- DOM rendering
- localStorage state
- approval bypass / auto execute / auto apply

### `web/js/atlas_state.js`
Owns:
- Atlas localStorage keys
- safe get/set/remove
- last subview / last run / requirement draft
- `window.AtlasState`

Must not own:
- fetch
- DOM rendering
- approval / execute / patch gate

### `web/js/atlas_ui.js`
Owns:
- Atlas subview DOM switching
- requirement status/char count
- workbench summary/collapse helpers
- `window.AtlasUI`

Must not own:
- fetch
- localStorage
- approval / execute / patch gate

## Echo modules
### `web/js/echo_api.js`
Owns:
- Echo / ASR / TTS / SBV2 / EchoVault HTTP wrappers
- `window.EchoAPI`

Must not own:
- WebSocket
- MediaRecorder
- DOM rendering
- audio playback

### `web/js/echo_stream.js`
Owns:
- Echo recording/connection/playback state holder
- WebSocket/media object references as state
- `window.EchoStream`

Must not own:
- HTTP API
- DOM rendering
- direct audio playback
- settings storage

### `web/js/echo_ui.js`
Owns:
- Echo status/connection/vault/model/session rendering helpers
- `window.EchoUI`

Must not own:
- HTTP API
- WebSocket
- MediaRecorder
- direct audio playback
- localStorage

## Runtime diagnostics
### `web/js/runtime_diagnostics.js`
Owns:
- Read-only diagnostics endpoint collection
- secret masking
- short/detailed JSON formatting
- `window.RuntimeDiagnostics`

Must not own:
- POST operations
- model load/unload/start/stop
- heavy probes
- runtime mutation

## Feature manifest
### `web/feature_manifest.json`
Owns:
- Static selector inventory
- tabs/root panels/required controls
- storage key inventory
- module script metadata

Must not own:
- behavior
- runtime execution logic

## Tests
Main contract tests:
- `tests/test_ui_module_loader_contract.py`
- `tests/test_atlas_api_module_contract.py`
- `tests/test_atlas_state_module_contract.py`
- `tests/test_atlas_ui_module_contract.py`
- `tests/test_atlas_inline_cleanup_contract.py`
- `tests/test_echo_api_module_contract.py`
- `tests/test_echo_stream_module_contract.py`
- `tests/test_echo_ui_module_contract.py`
- `tests/test_runtime_diagnostics_module_contract.py`
- `tests/test_feature_manifest_contract.py`
- `tests/test_playwright_manifest_loader_contract.py`

## Future work
- Move remaining large Atlas renderers only with contract coverage
- Move remaining Echo session/model rendering deeper only with contract coverage
- Remove deprecated shims only after Playwright confirms no callers remain
- Keep `ui.html` as DOM skeleton until further modularization is planned
