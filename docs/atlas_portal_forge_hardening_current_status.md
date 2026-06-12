# Atlas Portal + Model Forge Hardening — Current Status

> Mutable checkpoint for Codex / Claude Goal mode.
> Update after every coherent PFH package.

## Program state

- Overall: **ACTIVE — POST-PFG PRODUCTION HARDENING**
- Active track: `PFH-1..PFH-8`
- Current package: `PFH-6`
- Current package goal: run real evidence through the Forge provider/preset runner path.
- Rollout: Forge remains off/default unless bridge-level shadow/cutover evidence proves otherwise.
- Legacy model execution remains available as fallback until consumer-zero, benchmark, shadow, rollback, and migration gates pass.
- OpenRouter live evidence remains unavailable unless explicitly configured.

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_portal_forge_current_status.md`
3. `docs/atlas_portal_forge_hardening_current_status.md`
4. `docs/atlas_portal_forge_hardening_plan.md`
5. current PFH package in the hardening plan
6. `docs/atlas_portal_forge_hardening_test_plan.md`
7. `docs/atlas_portal_forge_hardening_agent_entrypoint.md`
8. relevant Portal Forge design/test/current-status docs
9. target code, public contracts, direct callers, dependencies, and tests

## Package table

| Package | Goal | Status |
|---|---|---|
| PFH-1 | Benchmark preset identity and execution semantics | acceptance_complete |
| PFH-2 | OpenRouter catalog product integration | acceptance_complete |
| PFH-3 | Provider configured state vs runtime readiness | acceptance_complete |
| PFH-4 | ForgeModelExecutionBridge, shadow-first | acceptance_complete |
| PFH-5 | Real cutover and rollback | acceptance_complete |
| PFH-6 | Real evidence through Forge provider/preset runner | in_progress |
| PFH-7 | Actual Portal runtime replay for Capsule evidence | not_started |
| PFH-8 | Guarded Candidate-to-Proposal handoff | not_started |

## Known review findings to address

```text
1. Forge cutover updates StageMatrix policy but does not yet prove the actual Atlas model execution data path is switched. [PFH-4/PFH-5 addressed for bridge path; PFH-6 real provider evidence still required]
2. LegacyAtlasProvider is not wired as a live ForgeService execution backend for current Atlas calls. [PFH-4 addressed for central legacy-primary bridge observation]
3. OpenRouterCatalog exists but is not fully product-connected to ForgeService/API/UI model selection. [PFH-2 addressed]
4. Benchmark UI primary preset IDs can diverge from real backend preset IDs. [PFH-1 addressed]
5. Benchmark run can submit only the first selected preset. [PFH-1 addressed]
6. Some real evidence tests use direct urllib model calls rather than Forge provider/preset runner path.
7. Local provider health can be misleading if base_url exists but server is unreachable. [PFH-3 addressed]
8. Capsule replay evidence should be actual Portal/Play runtime evidence where applicable, not caller assertion only.
```

## Evidence requirements

For each package, record:

```text
Completed package:
Status:
Changed modules/files:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Real model evidence:
Portal runtime evidence:
OpenRouter evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
```

## Completed package: PFH-1 benchmark preset identity and execution semantics

Completed package: PFH-1
Status: acceptance_complete
Changed modules/files:
- `agent/model_forge/schema.py`
- `agent/model_forge/benchmark_presets.py`
- `agent/model_forge/arena_runner.py`
- `agent/model_forge/forge_service.py`
- `app/api/forge.py`
- `web/js/forge.js`
- `tests/test_model_forge_benchmark_presets.py`
- `tests/test_model_forge_arena_runner.py`
- `tests/test_forge_api.py`
- `tests/test_forge_benchmark_render.py`
- `tests/test_forge_benchmark_request_payload.py`
- `docs/atlas_portal_forge_hardening_current_status.md`

Behavior implemented:
- Backend preset listing now exposes stable `family_id` and backend-owned `primary_rank`.
- Forge Benchmark primary controls are derived from backend preset metadata and render real preset IDs such as `quick_standard`, `web_app_standard`, `repair_standard`, and `greenfield_standard`.
- UI render tests now consume `preset_listing()` instead of fake `quick` / `web_app` / `repair` / `greenfield` IDs.
- Benchmark run payload includes all selected preset IDs through `preset_ids` while retaining `preset_id` for backward compatibility.
- Arena run records persist `preset_ids` and `benchmark_depth`.
- Non-standard benchmark depth returns `benchmark_depth_unavailable_not_supported:<depth>` instead of pretending to run unsupported depth semantics.

Focused tests:
- `python -m pytest -q tests/test_model_forge_benchmark_presets.py tests/test_model_forge_arena_runner.py tests/test_forge_api.py tests/test_forge_benchmark_render.py tests/test_forge_benchmark_request_payload.py` -> 22 passed.

Syntax checks:
- `node --check web/js/forge.js` -> passed.
- `python -m compileall -q agent/model_forge app/api tests/test_forge_benchmark_request_payload.py` -> passed.
- `git diff --check` -> passed with CRLF normalization warnings only.

Affected tests:
- PowerShell glob invocation `python -m pytest -q tests/test_model_forge_*.py tests/test_forge_*.py` did not run because PowerShell did not expand the globs.
- Expanded invocation: `$files = @(Get-ChildItem tests -Filter 'test_model_forge_*.py' | ForEach-Object { $_.FullName }) + @(Get-ChildItem tests -Filter 'test_forge_*.py' | ForEach-Object { $_.FullName }); python -m pytest -q @files` -> 156 passed, 1 skipped.

Real model evidence:
- PFH-1 does not require model execution.
- Required user LLM code-review verification ran through `http://127.0.0.1:8080/v1/chat/completions` using `Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf` -> PASS, no blocking issues. This is advisory code review evidence, not runtime/model acceptance evidence.

Portal runtime evidence:
- Not applicable to PFH-1; no Portal runtime claim made.

Capsule replay evidence:
- Not applicable to PFH-1; no Capsule replay claim made.

OpenRouter evidence:
- Not applicable to PFH-1; OpenRouter live smoke not run and not claimed.

Unavailable checks:
- Non-standard benchmark depths are explicitly unavailable via `benchmark_depth_unavailable_not_supported:<depth>`.
- OpenRouter live evidence remains unavailable unless `FORGE_OPENROUTER_LIVE_SMOKE=1` and `OPENROUTER_API_KEY` are configured.

Safety invariants:
- Arena candidates remain `not_applied`; no Proposal / Safe Apply / Verification authority changed.
- Forge remains off by default; legacy model execution remains primary.
- No external provider default changed.
- No secrets persisted, logged, or returned.
- Unsupported depth is not reported as passed.

Remaining gaps:
- PFH-2 must add product-connected OpenRouter catalog and a Forge Settings surface for provider configuration without persisting secret token values.
- Local provider benchmark UX still needs to distinguish provider model ID from the legacy LLM storage folder configuration.

Next package: PFH-2 — OpenRouter catalog product integration plus Forge Settings provider configuration UX.
Blocker: none.

## Completed package: PFH-2 OpenRouter catalog product integration and Forge Settings

Completed package: PFH-2
Status: acceptance_complete
Changed modules/files:
- `agent/model_forge/forge_service.py`
- `app/api/forge.py`
- `web/js/forge.js`
- `web/css/app.css`
- `tests/test_forge_api.py`
- `tests/test_forge_benchmark_render.py`
- `tests/test_forge_settings_render.py`
- `docs/atlas_portal_forge_hardening_current_status.md`

Behavior implemented:
- Added Forge Settings API: `GET /api/forge/settings` and `POST /api/forge/settings`.
- Added Forge Settings UI tab/menu for Local provider and OpenRouter provider configuration.
- Persisted only non-secret provider settings under Forge settings: local base URL, provider model ID, local LLM storage folder, OpenRouter enabled flag, OpenRouter API key env name, OpenRouter base URL, and OpenRouter app metadata.
- Rejected secret-bearing settings payload keys such as `api_key`, `access_token`, `token`, `openrouter_api_key`, and `authorization`.
- Settings API reports OpenRouter credential configured/missing state without returning the secret value.
- Added `GET /api/forge/providers/openrouter/catalog`.
- Connected `OpenRouterCatalog` to `ForgeService` with public cache path `ca_data/model_forge/catalog/openrouter_models.json`.
- OpenRouter catalog endpoint serves cached public model metadata without an API key and without making live calls under Local Only.
- `/api/forge/models` includes cached OpenRouter catalog models with source `openrouter_catalog_cache`.
- Forge Benchmark model selector can show OpenRouter catalog models and still keeps a manual provider model ID input fallback.
- Benchmark Settings now distinguishes provider model ID from the legacy/local LLM storage folder.

Focused tests:
- `python -m pytest -q tests/test_forge_api.py tests/test_forge_benchmark_render.py tests/test_forge_settings_render.py tests/test_model_forge_openrouter_catalog.py tests/test_model_forge_openrouter_config.py` -> 32 passed.

Syntax checks:
- `node --check web/js/forge.js` -> passed.
- `python -m compileall -q agent/model_forge app/api tests/test_forge_settings_render.py` -> passed.
- `git diff --check` -> passed with CRLF normalization warnings only.

Affected tests:
- Expanded invocation: `$files = @(Get-ChildItem tests -Filter 'test_forge_*.py' | ForEach-Object { $_.FullName }) + @(Get-ChildItem tests -Filter 'test_model_forge_openrouter_*.py' | ForEach-Object { $_.FullName }); python -m pytest -q @files` -> 86 passed, 1 skipped.

Real model evidence:
- PFH-2 does not require model execution.
- Required user LLM code-review verification ran through `http://127.0.0.1:8080/v1/chat/completions` using `Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf` -> PASS, no blocking issues. This is advisory code review evidence, not runtime/model acceptance evidence.

Portal runtime evidence:
- Not applicable to PFH-2; no Portal runtime claim made.

Capsule replay evidence:
- Not applicable to PFH-2; no Capsule replay claim made.

OpenRouter evidence:
- Cached/offline OpenRouter catalog behavior is covered by tests and uses public model metadata only.
- Live OpenRouter smoke was not run because PFH-2 does not enable `FORGE_OPENROUTER_LIVE_SMOKE=1` or provide `OPENROUTER_API_KEY`; no live evidence claimed.

Unavailable checks:
- OpenRouter live evidence remains unavailable unless `FORGE_OPENROUTER_LIVE_SMOKE=1` and `OPENROUTER_API_KEY` are configured.
- OpenRouter catalog without cache and under Local Only reports `disabled` with a blocking reason instead of making a live call.

Safety invariants:
- Secret values are not persisted, logged, or returned by API.
- Local Only still blocks live OpenRouter calls.
- Forge remains off by default; legacy model execution remains primary.
- External providers remain disabled by default unless explicitly configured.
- Arena / Proposal / Safe Apply / Verification authority boundaries unchanged.

Remaining gaps:
- PFH-3 must split provider configured state from runtime readiness so configured local base URL does not imply live readiness.
- OpenRouter catalog refresh UI is basic; live fetch still requires policy/key configuration and is not claimed here.

Next package: PFH-3 — Provider configured state vs runtime readiness.
Blocker: none.

## Completed package: PFH-3 provider configured state vs runtime readiness

Completed package: PFH-3
Status: acceptance_complete
Changed modules/files:
- `agent/model_forge/__init__.py`
- `agent/model_forge/provider_base.py`
- `agent/model_forge/providers/local_openai_compatible.py`
- `agent/model_forge/forge_service.py`
- `app/api/forge.py`
- `web/js/forge.js`
- `web/css/app.css`
- `tests/test_model_forge_local_openai.py`
- `tests/test_forge_api.py`
- `tests/test_forge_benchmark_render.py`
- `tests/test_forge_provider_cards_render.py`
- `docs/atlas_portal_forge_hardening_current_status.md`

Behavior implemented:
- Extended provider health with `configured_state`, `runtime_health`, `last_probe_at`, and `last_probe_error`.
- Added `ConfiguredState` and `RuntimeHealth` exports.
- Local provider without base URL now reports `configured_state=missing_config`.
- Local provider with base URL but no successful probe now reports `configured_state=configured`, `runtime_health=not_probed`, and legacy `health=unavailable`.
- Local provider explicit runtime probe uses `GET {base_url}/v1/models` and records ready/unavailable/error without treating configured state as readiness.
- Added `POST /api/forge/providers/{provider_id}/probe`.
- Forge provider summaries expose configured/runtime/probe fields.
- Forge Overview UI displays Configured and Runtime state and provides a Probe action for non-legacy providers.

Focused tests:
- `python -m pytest -q tests/test_model_forge_provider_registry.py tests/test_model_forge_local_openai.py tests/test_forge_api.py tests/test_forge_provider_cards_render.py tests/test_forge_benchmark_render.py` -> 42 passed.

Syntax checks:
- `node --check web/js/forge.js` -> passed.
- `python -m compileall -q agent/model_forge app/api tests/test_forge_provider_cards_render.py` -> passed.
- `git diff --check` -> passed with CRLF normalization warnings only.

Affected tests:
- Expanded invocation: `$files = @(Get-ChildItem tests -Filter 'test_model_forge_*.py' | ForEach-Object { $_.FullName }) + @(Get-ChildItem tests -Filter 'test_forge_*.py' | ForEach-Object { $_.FullName }); python -m pytest -q @files` -> 170 passed, 1 skipped.

Real model evidence:
- PFH-3 does not require model execution.
- Required user LLM code-review verification ran through `http://127.0.0.1:8080/v1/chat/completions` using `Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf` -> PASS, no blocking issues. This is advisory code review evidence, not runtime/model acceptance evidence.

Portal runtime evidence:
- Not applicable to PFH-3; no Portal runtime claim made.

Capsule replay evidence:
- Not applicable to PFH-3; no Capsule replay claim made.

OpenRouter evidence:
- Not applicable to PFH-3; OpenRouter live smoke not run and not claimed.

Unavailable checks:
- Local provider with base URL but no probe reports `runtime_health=not_probed`, not `ready`.
- Local provider with no base URL reports `missing_config` and explicit probe remains offline-safe.
- Failed local provider probe records unavailable/error and `last_probe_error`.

Safety invariants:
- Disabled/unavailable providers still fail closed through `ProviderRegistry.execute`.
- Local Only and external-provider policy behavior unchanged.
- Forge remains off by default; legacy model execution remains primary.
- No secrets persisted, logged, or returned.

Remaining gaps:
- PFH-4 must connect Forge to the actual Atlas LLM execution boundary in disabled/shadow modes.
- PFH-5 must make real cutover/rollback consume the bridge path.

Next package: PFH-4 — ForgeModelExecutionBridge, shadow-first.
Blocker: none.

## Completed package: PFH-4 ForgeModelExecutionBridge, shadow-first

Completed package: PFH-4
Status: acceptance_complete
Changed modules/files:
- `agent/model_forge/execution_bridge.py`
- `agent/model_forge/__init__.py`
- `agent/model_forge/forge_service.py`
- `agent/model_forge/providers/local_openai_compatible.py`
- `agent/model_forge/providers/openrouter_client.py`
- `app/api/atlas_pipeline.py`
- `tests/test_forge_execution_bridge.py`
- `tests/test_atlas_api_pipeline.py`
- `docs/atlas_portal_forge_hardening_current_status.md`

Behavior implemented:
- Added `ForgeModelExecutionBridge` around the central `atlas_llm_json_fn` execution boundary.
- Disabled mode records `forge_disabled_legacy_primary`, returns legacy output, and does not execute Forge providers.
- Shadow-select mode returns legacy output while running eligible Forge providers through `ProviderRegistry` and recording `ShadowStore` comparison evidence.
- Bridge evidence records stage, route, provider/model selection, source/privacy mode, policy decision, shadow result, fallback/legacy-primary decision, and prompt byte counts without persisting prompt text.
- `ForgeService` now accepts a per-call prompt resolver so Atlas prompts are passed to Forge providers only in memory during the bridge call.
- Local and OpenRouter providers expose `run_and_capture()` for shadow comparison while preserving `execute_chat_completion()`.
- Atlas planning and patch proposal LLM paths resolve through the bridge with explicit stage/route/task metadata.
- Progress wrapping now uses `with_progress` capability so both raw `AtlasLLMJsonAdapter` and the bridge remain compatible.

Focused tests:
- `python -m pytest tests/test_forge_execution_bridge.py tests/test_atlas_api_pipeline.py::test_create_plan_pool_uses_registered_atlas_llm_json_fn tests/test_atlas_api_pipeline.py::test_create_plan_pool_records_forge_bridge_decision_at_llm_boundary tests/test_atlas_api_pipeline.py::test_create_plan_pool_falls_back_when_llm_json_fn_returns_none -q` -> 5 passed.
- After source-mode fallback adjustment: `python -m pytest tests/test_forge_execution_bridge.py -q` -> 2 passed.

Syntax checks:
- `python -m py_compile agent/model_forge/execution_bridge.py agent/model_forge/forge_service.py agent/model_forge/providers/local_openai_compatible.py agent/model_forge/providers/openrouter_client.py app/api/atlas_pipeline.py` -> passed.
- `python -m py_compile agent/model_forge/execution_bridge.py` -> passed after source-mode fallback adjustment.
- `python -m compileall -q agent/model_forge app/api/atlas_pipeline.py` -> passed.
- `git diff --check` -> passed with CRLF normalization warnings only.

Affected tests:
- Expanded invocation: `$forge = Get-ChildItem tests -Filter 'test_forge*.py' | ForEach-Object { $_.FullName }; $modelForge = Get-ChildItem tests -Filter 'test_model_forge*.py' | ForEach-Object { $_.FullName }; python -m pytest @($forge + $modelForge + @('tests/test_atlas_llm_json_adapter.py','tests/test_atlas_llm_json_streaming.py','tests/test_atlas_api_pipeline.py::test_create_plan_pool_uses_registered_atlas_llm_json_fn','tests/test_atlas_api_pipeline.py::test_create_plan_pool_records_forge_bridge_decision_at_llm_boundary','tests/test_atlas_api_pipeline.py::test_create_plan_pool_falls_back_when_llm_json_fn_returns_none')) -q` -> 194 passed, 1 skipped.

Real model evidence:
- Required user LLM code-review verification ran through `http://127.0.0.1:8080/v1/chat/completions` -> PASS, no required fixes. This is advisory code review evidence, not runtime/model acceptance evidence.
- PFH-4 bridge tests use mocked/local fake providers; live model runtime evidence through Forge provider path is deferred to PFH-6.

Portal runtime evidence:
- Not applicable to PFH-4; no Portal runtime claim made.

Capsule replay evidence:
- Not applicable to PFH-4; no Capsule replay claim made.

OpenRouter evidence:
- OpenRouter live smoke was not run because PFH-4 does not enable `FORGE_OPENROUTER_LIVE_SMOKE=1` or provide `OPENROUTER_API_KEY`; no live evidence claimed.

Unavailable checks:
- Live Forge provider/model evidence is not claimed in PFH-4; PFH-6 remains responsible for real evidence through Forge provider/preset runner.
- Portal runtime and Capsule replay evidence are unavailable/not applicable for PFH-4.
- OpenRouter live evidence remains unavailable unless `FORGE_OPENROUTER_LIVE_SMOKE=1` and `OPENROUTER_API_KEY` are configured.

Safety invariants:
- Legacy output remains primary in disabled and shadow-select modes.
- Shadow evidence is advisory and `changes_production_routing=false`.
- Local Only remains the default source mode and blocks external providers through provider policy.
- Prompts are not persisted in bridge evidence; only byte counts and routing metadata are stored.
- No secrets are persisted, logged, or returned.
- Proposal / Safe Apply / Verification authority boundaries unchanged.
- Legacy model execution paths are not deleted.

Remaining gaps:
- PFH-5 must consume cutover/rollback state in the bridge so acknowledged cutover can return Forge output with legacy fallback.
- PFH-6 must run real evidence through Forge provider or preset runner rather than adapter-only or direct urllib paths.

Next package: PFH-5 — Real cutover and rollback.
Blocker: none.

## Completed package: PFH-5 Real cutover and rollback

Completed package: PFH-5
Status: acceptance_complete
Changed modules/files:
- `agent/model_forge/execution_bridge.py`
- `tests/test_forge_execution_bridge.py`
- `tests/test_atlas_api_pipeline.py`
- `docs/atlas_portal_forge_hardening_current_status.md`

Behavior implemented:
- `ForgeModelExecutionBridge` now consumes active cutover records through `service.cutover_controller.load(stage)`.
- Active production-routing policy is ignored unless a cutover record is active and `forge_primary=true`.
- Before cutover, bridge returns legacy output and records legacy-primary/shadow evidence.
- After acknowledged cutover, bridge returns parsed Forge output for the selected stage and records `forge_primary_returned`.
- If Forge output is invalid or provider execution fails, bridge returns legacy output and records `forge_primary_failed_legacy_fallback`.
- Rollback returns the stage to shadow-select through `CutoverController.rollback`; bridge returns legacy output and records the rolled-back cutover state.
- Bridge event persistence strips transient routed data before writing evidence.

Focused tests:
- `python -m pytest tests/test_forge_execution_bridge.py tests/test_atlas_api_pipeline.py::test_create_plan_pool_cutover_returns_forge_output_at_llm_boundary -q` -> 6 passed.

Syntax checks:
- `python -m py_compile agent/model_forge/execution_bridge.py tests/test_forge_execution_bridge.py tests/test_atlas_api_pipeline.py` -> passed.
- `python -m compileall -q agent/model_forge app/api/atlas_pipeline.py` -> passed.
- `git diff --check` -> passed with CRLF normalization warnings only.

Affected tests:
- Expanded invocation: `$forge = Get-ChildItem tests -Filter 'test_forge*.py' | ForEach-Object { $_.FullName }; $modelForge = Get-ChildItem tests -Filter 'test_model_forge*.py' | ForEach-Object { $_.FullName }; python -m pytest @($forge + $modelForge + @('tests/test_atlas_llm_json_adapter.py','tests/test_atlas_llm_json_streaming.py','tests/test_atlas_api_pipeline.py::test_create_plan_pool_uses_registered_atlas_llm_json_fn','tests/test_atlas_api_pipeline.py::test_create_plan_pool_records_forge_bridge_decision_at_llm_boundary','tests/test_atlas_api_pipeline.py::test_create_plan_pool_cutover_returns_forge_output_at_llm_boundary','tests/test_atlas_api_pipeline.py::test_create_plan_pool_falls_back_when_llm_json_fn_returns_none')) -q` -> 198 passed, 1 skipped.

Real model evidence:
- PFH-5 cutover drill uses fake/local test providers to prove bridge behavior and fallback semantics.
- Required user LLM code-review verification ran through `http://127.0.0.1:8080/v1/chat/completions` -> PASS, no required fixes. This is advisory code review evidence, not runtime/model acceptance evidence.
- Live model evidence through the Forge provider/preset runner remains PFH-6 scope.

Portal runtime evidence:
- Not applicable to PFH-5; no Portal runtime claim made.

Capsule replay evidence:
- Not applicable to PFH-5; no Capsule replay claim made.

OpenRouter evidence:
- OpenRouter live smoke was not run because PFH-5 does not enable `FORGE_OPENROUTER_LIVE_SMOKE=1` or provide `OPENROUTER_API_KEY`; no live evidence claimed.

Unavailable checks:
- Live Forge provider/model evidence is not claimed in PFH-5; PFH-6 remains responsible for real provider/preset-runner evidence.
- Portal runtime and Capsule replay evidence are unavailable/not applicable for PFH-5.
- OpenRouter live evidence remains unavailable unless `FORGE_OPENROUTER_LIVE_SMOKE=1` and `OPENROUTER_API_KEY` are configured.

Safety invariants:
- Active cutover requires an active cutover record; StageMatrix alone is not enough.
- Legacy fallback remains available and is used on Forge failure.
- Rollback returns to legacy primary/shadow behavior.
- Transient routed Forge payload is not persisted in bridge evidence.
- Local Only remains default and provider selection still goes through provider policy.
- No secrets are persisted, logged, or returned.
- Proposal / Safe Apply / Verification authority boundaries unchanged.
- Legacy model execution paths are not deleted.

Remaining gaps:
- PFH-6 must provide real evidence through Forge provider or preset runner rather than fake providers or direct urllib paths.
- PFH-7 must base Capsule replay profile updates on actual Portal/Play runtime evidence.

Next package: PFH-6 — Real evidence through Forge provider/preset runner.
Blocker: none.

## Current package: PFH-6 checklist

- Add or extend a Forge provider/preset runner for real evidence.
- Ensure evidence runs through `ProviderRegistry`, a Forge provider, route selection, and candidate evaluation.
- Replace or complement direct urllib real-evidence paths with the Forge runner path.
- Record unavailable live provider checks truthfully.
- Keep OpenRouter live evidence gated by `FORGE_OPENROUTER_LIVE_SMOKE=1` and `OPENROUTER_API_KEY`.
- Do not claim Portal runtime or Capsule replay evidence unless actual runtime/replay runs.

## Stop conditions

Stop only for:

- destructive migration requiring explicit approval;
- changing default external-code exposure;
- removing legacy model execution path;
- safety/authority conflict with Proposal/Safe Apply/Verification;
- required live model/OpenRouter/Portal runtime unavailable with no truthful alternative.
