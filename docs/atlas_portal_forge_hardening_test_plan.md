# Atlas Portal + Model Forge Hardening — Test Plan

## Philosophy

This track exists because PFG completion created a solid foundation but left production-hardening gaps. Therefore tests must prove production connection, not just component behavior.

## Proof levels

```text
component_complete       -> schema/unit/component tests
production_connected     -> actual API/bridge/caller path uses the component
acceptance_complete      -> required runtime/model/cutover evidence is present
unavailable              -> required environment missing; never counts as passed
```

## PFH-1 tests

Required:

- backend preset listing exposes real primary presets;
- Forge UI renders Quick/Web App/Repair/Greenfield using real backend IDs;
- UI tests do not use fake IDs that can hide backend mismatch;
- multi-preset selection appears in the arena/benchmark request payload;
- depth either changes selected task set or returns unsupported/unavailable visibly.

Suggested tests:

```text
tests/test_model_forge_benchmark_presets.py
tests/test_forge_benchmark_render.py
tests/test_forge_benchmark_request_payload.py
```

## PFH-2 tests

Required:

- OpenRouter catalog endpoint exists;
- mock catalog fetch populates cache;
- cache can be read without API key;
- missing key is disabled/unavailable, not passed;
- no secret in API response;
- UI selector can render catalog model IDs.

## PFH-3 tests

Required:

- local provider base_url only means configured, not runtime_ready;
- probe success changes runtime_health to ready;
- probe failure changes runtime_health to unavailable/error;
- CI does not call live network unless explicitly requested.

## PFH-4 tests

Required:

- disabled mode calls legacy only;
- shadow mode returns legacy output and records Forge shadow result when available;
- Forge failure in shadow mode does not alter returned output;
- bridge records stage/model/provider/route/policy/fallback evidence;
- integration test uses the central Atlas model execution boundary.

## PFH-5 tests

Required:

- before cutover, bridge returns legacy;
- after acknowledged cutover, bridge returns Forge for selected stage;
- Forge failure falls back to legacy;
- rollback returns legacy primary;
- cutover evidence persists.

## PFH-6 tests

Required:

- Quick/Web App/Repair/Greenfield evidence tests call provider/runner/bridge;
- no direct urllib orchestration outside provider/mock infrastructure;
- unavailable local model server is skipped truthfully;
- mechanical tests or Portal runtime decide success.

## PFH-7 tests

Required:

- Capsule replay actually installs/runs when runtime is available;
- runtime success/failure/unavailable are distinct;
- profile update uses replay evidence;
- package ZIP remains immutable.

## PFH-8 tests

Required:

- eligible candidate creates Proposal draft only;
- ineligible candidate is blocked with reasons;
- no Safe Apply or source mutation happens;
- Proposal draft includes candidate/evaluator/risk/privacy metadata.

## Milestone suite

After PFH-8, run:

```text
python -m pytest -q tests/test_model_forge_*.py
python -m pytest -q tests/test_forge_*.py
python -m pytest -q tests/test_portal_*.py
node --check web/js/forge.js
node --check web/js/portal.js
```

If local model server is available, also run the real local evidence suite through Forge provider/runner. If unavailable, record unavailable, not passed.

If OpenRouter live smoke is configured, run it with `FORGE_OPENROUTER_LIVE_SMOKE=1` and `OPENROUTER_API_KEY`. Otherwise record unavailable.
