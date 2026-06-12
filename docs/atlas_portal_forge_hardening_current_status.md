# Atlas Portal + Model Forge Hardening — Current Status

> Mutable checkpoint for Codex / Claude Goal mode.
> Update after every coherent PFH package.

## Program state

- Overall: **ACTIVE — POST-PFG PRODUCTION HARDENING**
- Active track: `PFH-1..PFH-8`
- Current package: `PFH-2`
- Current package goal: OpenRouter catalog product integration and Forge Settings entry for provider configuration, without persisting or returning secrets.
- Rollout: Forge remains off/default unless bridge-level shadow/cutover evidence proves otherwise.
- Legacy model execution remains primary until PFH-4/PFH-5 evidence passes.
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
| PFH-2 | OpenRouter catalog product integration | in_progress |
| PFH-3 | Provider configured state vs runtime readiness | not_started |
| PFH-4 | ForgeModelExecutionBridge, shadow-first | not_started |
| PFH-5 | Real cutover and rollback | not_started |
| PFH-6 | Real evidence through Forge provider/preset runner | not_started |
| PFH-7 | Actual Portal runtime replay for Capsule evidence | not_started |
| PFH-8 | Guarded Candidate-to-Proposal handoff | not_started |

## Known review findings to address

```text
1. Forge cutover updates StageMatrix policy but does not yet prove the actual Atlas model execution data path is switched.
2. LegacyAtlasProvider is not wired as a live ForgeService execution backend for current Atlas calls.
3. OpenRouterCatalog exists but is not fully product-connected to ForgeService/API/UI model selection.
4. Benchmark UI primary preset IDs can diverge from real backend preset IDs. [PFH-1 addressed]
5. Benchmark run can submit only the first selected preset. [PFH-1 addressed]
6. Some real evidence tests use direct urllib model calls rather than Forge provider/preset runner path.
7. Local provider health can be misleading if base_url exists but server is unreachable.
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

## Current package: PFH-2 checklist

- Inspect existing OpenRouter config/client/catalog modules and Forge API/service wiring.
- Add Forge Settings tab/menu for non-secret provider settings and secret-safe configured-state display.
- Do not persist OpenRouter access token values; only show configured/missing state and credential env name or one-shot probe behavior.
- Connect `OpenRouterCatalog` to ForgeService/API/UI model selection.
- Store public catalog cache under `ca_data/model_forge/catalog/openrouter_models.json`.
- Keep Local Only mode blocking external calls.
- Make benchmark model/provider UX distinguish provider model ID from local model storage folder configuration.
- Update tests and this status with exact evidence.

## Stop conditions

Stop only for:

- destructive migration requiring explicit approval;
- changing default external-code exposure;
- removing legacy model execution path;
- safety/authority conflict with Proposal/Safe Apply/Verification;
- required live model/OpenRouter/Portal runtime unavailable with no truthful alternative.
