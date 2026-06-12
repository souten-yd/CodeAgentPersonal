# Atlas Portal + Model Forge Hardening Plan

This document records the post-PFG implementation review follow-up plan. It is intended for Goal-mode agents after reading `AGENTS.md` and the existing Portal Forge documents.

## Summary

`PFG-0..PFG-38` established the Portal + Forge foundation, UI, provider abstractions, OpenRouter components, Arena, profiles, Portal trace, Capsule metadata, and evidence gates.

Code review found that the foundation is real, but the production Atlas model execution path is still legacy-primary and Forge is not yet the effective data-plane selector. The main gap is not "more UI"; it is wiring Forge into the real Atlas model execution boundary with shadow-first evidence, reversible cutover, and legacy fallback.

The goal of this hardening track is to convert the existing Forge control plane into a production-connected, evidence-driven model execution path without weakening Safe Apply, Portal runtime, external-provider safety, or legacy rollback.

## Current truth baseline

Observed from the current codebase review:

- Forge service and UI exist.
- Provider registry, local provider, OpenRouter config/client/catalog components exist.
- Arena and CandidateEvaluator exist.
- Portal x Forge trace and Capsule metadata/replay components exist.
- PFG current status records real local evidence, Portal evidence, and Capsule replay evidence.
- Forge cutover currently changes StageMatrix policy, not necessarily the central Atlas model execution data path.
- Legacy model execution remains primary; legacy retirement is blocked because consumers remain.
- OpenRouter live smoke is unavailable unless configured with explicit key/env.
- Some real evidence tests call local models directly with urllib rather than through the Forge provider/preset runner path.
- Benchmark UI appears to use primary preset aliases that can diverge from real backend preset IDs.

## Core hardening goal

Make this statement true with code and evidence:

```text
Atlas model execution can ask Forge for a stage-aware model execution decision.
In disabled/shadow mode, legacy output remains primary and Forge evidence is recorded.
After an explicit cutover, selected stages can return Forge output with legacy fallback.
Rollback restores legacy primary.
Real evidence tests run through the same bridge/provider/preset path used by production.
```

## Hardening packages

### PFH-1 — Benchmark preset identity and execution semantics

Fix mismatch between UI primary preset IDs and real backend preset IDs. The UI must derive primary preset controls from `/api/forge/presets` output, not from fake hard-coded IDs. Multi-preset selection and depth must be reflected in the run request or clearly treated as unavailable.

Implementation requirements:

- Add stable preset family aliases if needed, for example `family_id=quick`, `preset_id=quick_standard`.
- Update Forge UI so primary controls are selected from backend presets by category/family/display name, not hard-coded fake IDs.
- Update tests so they use `preset_listing()` or the API response shape, not custom fake IDs.
- Update Arena/benchmark request payload to include all selected preset IDs or introduce a batch endpoint.
- Implement depth semantics, or expose depth as `unavailable_not_supported` until the runner supports it.

Acceptance:

- Quick/Web App/Repair/Greenfield appear as primary controls using real preset IDs.
- UI tests consume real `preset_listing()` output.
- Multi-selection is included in request payload.
- Depth is implemented or explicitly unavailable, not cosmetic.
- The UI does not silently submit only the first selected preset unless the backend contract explicitly says so.

### PFH-2 — OpenRouter catalog product integration

Connect OpenRouterCatalog to ForgeService, API, and UI.

Implementation requirements:

- Instantiate OpenRouterCatalog from ForgeService or a dedicated catalog service.
- Store cache under `ca_data/model_forge/catalog/openrouter_models.json`.
- Add API endpoint: `GET /api/forge/providers/openrouter/catalog`.
- Include OpenRouter catalog models in `/api/forge/models` when cache exists or policy permits.
- Return disabled, unavailable, from_cache, and live states distinctly.
- UI model selector should display catalog-backed models when available and fall back to manual model ID entry when not.

Acceptance:

- `GET /api/forge/providers/openrouter/catalog` exists.
- `/api/forge/models` can include cached OpenRouter models without secrets.
- Disabled/missing-key/network failure returns disabled/unavailable/from_cache truthfully.
- UI model selector can use catalog models when available.
- OpenRouter catalog cache remains public metadata only and never includes credentials.

### PFH-3 — Provider configured state vs runtime readiness

Split provider status into configured state and runtime health. A local base URL should not equal runtime-ready unless a probe succeeds.

Implementation requirements:

- Add provider status fields:
  - `configured_state`: disabled / missing_config / configured
  - `runtime_health`: not_probed / ready / unavailable / error
  - `last_probe_at`
  - `last_probe_error`
- Add explicit probe endpoint: `POST /api/forge/providers/{provider_id}/probe`.
- Keep CI offline by default; mock probe tests should not require a live server.
- UI should show "Configured" separately from "Ready".

Acceptance:

- Local provider with only base_url is configured, not runtime-ready.
- Explicit probe endpoint exists and is offline-safe by default.
- UI displays Configured/Ready/Unavailable/Disabled distinctly.
- Provider health summaries do not mislead the user into thinking a dead server is ready.

### PFH-4 — ForgeModelExecutionBridge, shadow-first

Add a central bridge at the Atlas model execution boundary. The bridge wraps legacy `atlas_llm_json_fn` and Forge provider execution.

Implementation requirements:

- Add module such as `agent/model_forge/execution_bridge.py`.
- The bridge must accept:
  - stage
  - route/task category
  - output contract
  - request/context metadata
  - legacy callable
  - provider registry / ForgeService
- Disabled mode:
  - call legacy only
  - record no Forge production routing
- Shadow mode:
  - call legacy as primary
  - optionally call Forge as shadow if policy/provider available
  - store shadow evidence
  - return legacy output
- Auto/cutover mode:
  - call Forge as primary only when cutover is acknowledged and policy allows
  - fallback to legacy on Forge failure
  - record fallback evidence
- Integrate at the central Atlas LLM JSON execution boundary, not scattered individual call sites.

Acceptance:

- Disabled and shadow modes preserve legacy output as primary.
- Shadow output is recorded when available.
- No scattered call-site rewrites.
- No production routing change unless stage policy and cutover allow it.
- The bridge records exact stage, route, model, provider, policy, and fallback decisions.

### PFH-5 — Real cutover and rollback

Make cutover affect the actual bridge path, not only StageMatrix storage.

Implementation requirements:

- Update `CutoverController` or the caller path so cutover state is consumed by `ForgeModelExecutionBridge`.
- Add tests that exercise the same bridge used by production Atlas calls:
  - before cutover, legacy output is returned;
  - after acknowledged cutover, Forge output is returned for the selected stage;
  - if Forge fails, legacy fallback is used;
  - rollback returns to legacy primary.
- Ensure fallback and rollback evidence is persisted.
- Do not remove legacy execution.

Acceptance:

- Before cutover, legacy output is returned.
- After acknowledged cutover, Forge output is returned for the selected stage.
- If Forge fails, legacy fallback is used.
- Rollback returns to legacy primary.
- Cutover evidence includes at least one integration test that exercises the same bridge used by production Atlas calls.

### PFH-6 — Real evidence through Forge provider/preset runner

Replace direct urllib model calls in real evidence tests with the Forge provider/preset runner path.

Implementation requirements:

- Add `PresetRunner` or similar that executes tasks through:
  - ProviderRegistry
  - LocalOpenAICompatibleProvider or configured provider
  - RouteSelector
  - CandidateEvaluator
  - optional Portal runtime for runnable artifacts
- Convert existing real Quick/Web App/Repair/Greenfield evidence tests to use this runner/bridge.
- Keep direct urllib helpers only inside provider implementations or mock server utilities, not test orchestration.
- Skip truthfully when no local model server is available.

Acceptance:

- Quick/Web App/Repair/Greenfield real evidence goes through ProviderRegistry/LocalOpenAICompatibleProvider or the bridge.
- Mechanical or Portal runtime verdicts decide success.
- Unavailable model server skips truthfully.
- Evidence artifacts identify provider, model, preset, route, bridge/runner path, and runtime verdict.

### PFH-7 — Actual Portal runtime replay for Capsule evidence

Capsule replay must obtain runtime evidence where applicable. A caller-supplied `runtime_passed=True` alone is not sufficient for acceptance-level replay proof.

Implementation requirements:

- Add replay path that installs and runs a Capsule through PortalRuntimeService or Play runtime.
- Capture actual runtime outcome:
  - preview URL served
  - HTTP status / process status
  - log errors
  - timeout/unavailable
- Feed actual replay evidence into Forge profile updater.
- Preserve package ZIP immutability and sidecar-only Forge metadata.

Acceptance:

- Replay installs/runs through PortalRuntimeService or Play runtime.
- Success/failure/unavailable are distinct.
- Package ZIP remains immutable.
- Profile updates are based on actual replay evidence.

### PFH-8 — Guarded Candidate-to-Proposal handoff

Add a safe handoff from eligible Arena candidate to Proposal draft. It must not apply changes.

Implementation requirements:

- Add endpoint such as `POST /api/forge/arena/candidates/{candidate_id}/proposal-draft`.
- It creates a draft Proposal artifact only.
- The artifact records:
  - candidate ID
  - Arena run ID
  - provider/model/route/preset
  - evaluator score
  - blocked reasons
  - risk/privacy metadata
  - required Safe Apply and Verification steps
- UI action should be labeled "Create Proposal draft" and disabled for blocked candidates.
- No direct apply button.

Acceptance:

- Endpoint creates a draft Proposal artifact only.
- Safe Apply authority is unchanged.
- UI labels action as approval-required.
- Ineligible candidates expose blocked reasons.
- Proposal artifact records candidate ID, Arena run ID, evaluator score, risk, privacy policy, and required verification steps.

## Required evidence discipline

For every PFH package:

- Update `docs/atlas_portal_forge_hardening_current_status.md` with exact commands and results.
- Separate mock, component, local model, Portal runtime, Capsule replay, OpenRouter live, cutover, and retirement evidence.
- Keep `unavailable` distinct from `passed`.
- Do not claim OpenRouter live evidence without `FORGE_OPENROUTER_LIVE_SMOKE=1` and `OPENROUTER_API_KEY`.
- Do not retire legacy paths until consumer-zero, benchmark, shadow, rollback, and migration gates pass.
- Use LLMs for review/evaluation only as advisory or comparative evidence; mechanical tests and real runtime evidence remain authoritative.

## Suggested execution order

1. PFH-1
2. PFH-4
3. PFH-5
4. PFH-2
5. PFH-3
6. PFH-6
7. PFH-7
8. PFH-8

## Completion definition

The hardening track is complete only when:

- PFH-1..PFH-8 are acceptance_complete or explicitly deferred with truthful evidence.
- Forge model execution is connected to the actual Atlas model execution boundary in shadow mode.
- At least one stage has a tested, reversible Forge-primary cutover path with legacy fallback.
- Real evidence tests run through the Forge provider/preset runner or bridge path.
- Capsule replay profile updates are based on actual Portal/Play runtime evidence.
- OpenRouter catalog is product-connected without secrets and without claiming live evidence unless live smoke actually ran.
