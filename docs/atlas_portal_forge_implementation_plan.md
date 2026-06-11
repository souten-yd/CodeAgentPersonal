# Atlas Portal + Model Forge — Implementation Plan

## Status model

Use the same proof levels as PIR:

```text
not_started
in_progress
component_complete
production_connected
acceptance_complete
blocked
```

Do not use plain `Completed` in current status records.

## Execution policy

- Execute packages sequentially unless a current status file explicitly changes the active package.
- Keep every PR reversible until evidence proves cutover.
- Prefer small vertical slices, but do not stop at planning.
- Update `docs/atlas_portal_forge_current_status.md` after every coherent slice.
- Do not delete legacy execution paths until retirement gates pass.
- Do not claim OpenRouter/live-model evidence without actually running it.
- Do not claim Portal runtime behavior from UI-only tests.
- Do not apply Arena candidates directly; all adoption goes through Proposal/Safe Apply/Verification.

## Package overview

```text
PFG-0   baseline and design acceptance
PFG-1   Portal polish audit and compatibility gates
PFG-2   Portal import upload endpoint and UI
PFG-3   Portal snapshot listing and start-from-snapshot UI
PFG-4   legacy package manifest sidecar repair
PFG-5   Forge core schemas and taxonomies
PFG-6   provider base and registry
PFG-7   Legacy Atlas Executor adapter
PFG-8   local OpenAI-compatible provider adapter
PFG-9   OpenRouter configuration and secret policy
PFG-10  OpenRouter mock chat client
PFG-11  OpenRouter model catalog cache
PFG-12  provider health and Source Mode policy
PFG-13  benchmark preset schema and initial presets
PFG-14  Arena runner foundation
PFG-15  Candidate Evaluator foundation
PFG-16  Model Profile Store and profile updater
PFG-17  Stage Matrix policy and selector
PFG-18  Route Matrix policy and selector
PFG-19  Forge backend API
PFG-20  Forge top-level nav and shell UI
PFG-21  Forge Overview and Provider cards
PFG-22  Skill Radar and Leaderboard UI
PFG-23  Benchmark Preset selector UI
PFG-24  Arena UI
PFG-25  Stage Matrix and Route Matrix UI
PFG-26  Loadouts UI and persistence
PFG-27  Portal Run Forge Trace metadata
PFG-28  Portal evidence to Candidate Evaluator
PFG-29  Capsule Forge metadata and replay
PFG-30  real local-model Quick preset run
PFG-31  real Web App / Portal run preset
PFG-32  real Repair preset run
PFG-33  real Greenfield Capsule replay run
PFG-34  optional OpenRouter live smoke gate
PFG-35  stage shadow evidence for patch/test/failure/repair
PFG-36  controlled Forge primary cutover for selected stage
PFG-37  legacy retirement gates and consumer registry
PFG-38  final milestone benchmark and docs
```

The goal feature should continue beyond any single package until the current status file marks PFG-38 `acceptance_complete` or a truthful stop condition is reached.

---

## PFG-0 — Baseline and design acceptance

Goal: land canonical docs and active status.

Files:

```text
docs/atlas_portal_forge_master_goal.md
docs/atlas_portal_forge_detailed_design.md
docs/atlas_portal_forge_implementation_plan.md
docs/atlas_portal_forge_test_plan.md
docs/atlas_portal_forge_current_status.md
docs/atlas_portal_forge_agent_entrypoint.md
AGENTS.md
```

Acceptance:

- docs identify Portal as existing completed baseline, not missing implementation;
- docs inherit PIR-style proof gates;
- AGENTS.md points agents to the new Portal Forge goal without deleting PIR instructions;
- no runtime behavior changes.

---

## PFG-1 — Portal polish audit and compatibility gates

Goal: verify current Portal state and lock remaining polish gaps.

Tasks:

- Re-read `docs/atlas_play_portal_capsule_current_status.md` and current code.
- Verify current Portal nav, `web/js/portal.js`, API client surface, and data lifecycle tests.
- Record actual remaining gaps:
  - browser upload import;
  - snapshot-list/start-from-snapshot selector;
  - legacy manifest sidecar repair;
  - Forge trace UX placeholder.
- Add regression tests that ensure existing Save/Snapshot/Discard, Export data-free, quarantine, and no free-form command behavior remain intact.

Acceptance:

- focused Portal tests pass;
- UI contract tests for Portal nav still pass or pre-existing failures are documented;
- current status updated with exact evidence.

---

## PFG-2 — Portal import upload endpoint and UI

Goal: allow browser upload import instead of server-side archive path only.

Tasks:

- Add a safe upload endpoint for Capsule package archives.
- Enforce size limit, extension/type checks, temp staging, path quarantine, and manifest validation.
- Add Portal UI upload control with clear trust warning.
- Preserve existing server-path import for developer workflows if safe.

Acceptance:

- unsafe paths and unsafe archives fail closed;
- package archive is not trusted until quarantine and manifest checks pass;
- import UI works on mobile;
- package export still excludes runtime data.

---

## PFG-3 — Portal snapshot listing and start-from-snapshot UI

Goal: expose existing snapshot data lifecycle in the run selector.

Tasks:

- Add snapshot list API for package/run data where supported.
- Add Start from snapshot option in Portal run sheet.
- Preserve Save-as-snapshot during run.
- Add empty-state and missing snapshot handling.

Acceptance:

- snapshot list unavailable is shown truthfully;
- starting from a snapshot restores data state in a new run;
- discard still destroys ephemeral/snapshot-started run data according to policy.

---

## PFG-4 — Legacy package manifest sidecar repair

Goal: make older package records usable in Portal catalog when possible.

Tasks:

- Add a read-only manifest sidecar repair command/API.
- Infer launch profiles only from immutable package content and safe metadata.
- Never mutate existing package ZIPs.
- Mark unrecoverable packages clearly.

Acceptance:

- legacy records with recoverable manifests show profiles;
- unrecoverable records show safe unavailable state;
- no package archive mutation.

---

## PFG-5 — Forge core schemas and taxonomies

Goal: introduce pure schema/taxonomy code with no production behavior change.

Tasks:

- Implement ProviderDescriptor, ModelDescriptor, ModelProfile, BenchmarkPreset, ArenaCandidate, CandidateScore, ForgeExecutionRequest, ForgeExecutionResult.
- Implement stage and route enum/taxonomy helpers.
- Implement source/privacy policy enum helpers.

Acceptance:

- unit tests for schema roundtrip and invalid values;
- no external calls;
- no production routing behavior change.

---

## PFG-6 — Provider base and registry

Goal: introduce provider abstraction.

Tasks:

- Add Provider interface.
- Add registry with disabled-by-default external provider support.
- Add health state: ready, disabled, unavailable, error.
- Add redacted logging helper.

Acceptance:

- registry tests prove missing credentials do not crash;
- disabled providers are never executed;
- unavailable is recorded separately from failed.

---

## PFG-7 — Legacy Atlas Executor adapter

Goal: wrap the existing model execution path as a Forge provider.

Tasks:

- Inventory actual model execution callers first.
- Create LegacyAtlasProvider that converts ForgeExecutionRequest into the existing call path.
- Keep legacy path primary; Forge only observes or shadows.
- Preserve existing behavior.

Acceptance:

- adapter contract tests pass;
- affected existing model/planner tests pass;
- no stage cutover yet.

---

## PFG-8 — Local OpenAI-compatible provider adapter

Goal: support local/self-hosted OpenAI-compatible servers.

Tasks:

- Implement provider using base URL and local model IDs.
- Support non-streaming first.
- Add timeout and error classification.
- Avoid assuming external cloud.

Acceptance:

- mock server tests pass;
- local provider can be disabled/unavailable safely;
- no network call in CI unless test-local mock is running.

---

## PFG-9 — OpenRouter configuration and secret policy

Goal: register OpenRouter config safely.

Tasks:

- Add config model for OpenRouter.
- Read API key only from `OPENROUTER_API_KEY`.
- Add optional HTTP referer/app title envs.
- Add Source Mode and privacy gating before request creation.

Acceptance:

- key never persisted;
- logs redact secrets;
- OpenRouter disabled by default;
- Local Only blocks OpenRouter.

---

## PFG-10 — OpenRouter mock chat client

Goal: implement OpenRouter client behind provider interface.

Tasks:

- Implement chat completions call with bounded timeout.
- Add request/response normalization.
- Capture usage/latency/error data.
- Mock all tests.

Acceptance:

- CI uses mock HTTP only;
- no live API call unless explicit live smoke flags exist;
- provider errors become structured unavailable/error results.

---

## PFG-11 — OpenRouter model catalog cache

Goal: sync model list into Forge catalog.

Tasks:

- Add model catalog fetcher using OpenRouter models endpoint.
- Add cache with TTL and offline fallback.
- Store only public model metadata, not secrets.

Acceptance:

- mock catalog tests pass;
- offline fallback works;
- catalog fetch unavailable is not passed.

---

## PFG-12 — Provider health and Source Mode policy

Goal: centralize provider selection constraints.

Tasks:

- Implement source mode policy resolver.
- Implement privacy policy validator.
- Implement provider availability matrix.
- Add API-ready summaries for UI.

Acceptance:

- external provider cannot be selected when policy forbids it;
- source/privacy decisions are recorded in evidence.

---

## PFG-13 — Benchmark preset schema and initial presets

Goal: introduce selectable evaluation presets.

Tasks:

- Implement preset loader.
- Add Quick, Web App, Repair, Greenfield presets.
- Add validation that tasks declare evaluators and runtime budget.

Acceptance:

- preset listing API-ready data generated;
- no model execution required yet.

---

## PFG-14 — Arena runner foundation

Goal: run model x route candidates in non-applying mode.

Tasks:

- Implement arena run records.
- Execute candidates through provider interface.
- Persist raw outputs and metadata.
- Ensure candidates default to not_applied.

Acceptance:

- mock candidates run;
- no source mutation;
- no Safe Apply bypass.

---

## PFG-15 — Candidate Evaluator foundation

Goal: evaluate candidates mechanically.

Tasks:

- Contract parse and schema checks.
- Syntax/static checks where available.
- Risk/minimality placeholders with explicit unavailable markers.
- Scoring aggregation and rejection reasons.

Acceptance:

- invalid outputs rejected;
- unavailable evaluators not treated as passed;
- LLM judge not required.

---

## PFG-16 — Model Profile Store and profile updater

Goal: persist model skill results.

Tasks:

- Store versioned profiles under `ca_data/model_forge/profiles`.
- Store evidence references.
- Add profile update from candidate score.
- Add weak feedback flags for user save/discard/capsule decisions.

Acceptance:

- profile updates are append-only or versioned;
- raw evidence is preserved;
- scores can be recomputed.

---

## PFG-17 — Stage Matrix policy and selector

Goal: select models by stage under policy.

Tasks:

- Implement stage policy storage.
- Add disabled/fixed/shadow/auto/arena/fallback modes.
- Default to disabled or shadow.
- Record selection reasons.

Acceptance:

- no automatic cutover;
- policy explanations are visible to API/UI.

---

## PFG-18 — Route Matrix policy and selector

Goal: select routes by change class and profile.

Tasks:

- Implement route matrix.
- Connect change class/task category to route candidates.
- Keep critical_gate for unsafe tasks.

Acceptance:

- large/critical tasks cannot be forced through unsafe micro routes;
- route decisions are evidence-recorded.

---

## PFG-19 — Forge backend API

Goal: expose Forge to UI.

Endpoints:

```text
GET  /api/forge/status
GET  /api/forge/providers
GET  /api/forge/models
GET  /api/forge/profiles
GET  /api/forge/leaderboard
GET  /api/forge/presets
POST /api/forge/arena/run
GET  /api/forge/arena/runs/{id}
GET  /api/forge/stage-policy
POST /api/forge/stage-policy
GET  /api/forge/route-policy
POST /api/forge/route-policy
GET  /api/forge/loadouts
POST /api/forge/loadouts
```

Acceptance:

- secrets never returned;
- disabled/unavailable states visible;
- API tests pass.

---

## PFG-20 — Forge top-level nav and shell UI

Goal: add modern Forge tab without breaking Portal.

Tasks:

- Add top-level Forge nav between Echo and Portal or before Portal.
- Add mobile Forge tab.
- Keep default view simple.

Acceptance:

- node syntax checks;
- inline script syntax check;
- mobile viewport smoke;
- Portal nav remains functional.

---

## PFG-21 — Forge Overview and Provider cards

Goal: first usable UI.

Cards:

- Active Loadout.
- Source Mode.
- Provider health.
- OpenRouter status.
- Local provider status.
- Legacy Atlas status.

Acceptance:

- UI works with no configured external provider;
- OpenRouter missing key is shown as disabled/unavailable, not error spam.

---

## PFG-22 — Skill Radar and Leaderboard UI

Goal: show model strengths without complexity.

Tasks:

- Add champion cards.
- Add radar/list hybrid display.
- Add model detail drawer.

Acceptance:

- empty profiles show useful empty state;
- profile scores render compactly on mobile.

---

## PFG-23 — Benchmark Preset selector UI

Goal: let user choose preset/depth/model/provider.

Tasks:

- Quick/Web App/Repair/Greenfield checkboxes.
- Depth segmented control.
- Model/provider selection from registry.
- Policy warning for external providers.

Acceptance:

- user can run mock/local preset when available;
- full/deep is not forced by default.

---

## PFG-24 — Arena UI

Goal: display candidate comparison.

Tasks:

- Arena run sheet.
- Candidate rows with score/test/risk/latency/cost/privacy.
- Winner indication.
- Link to Portal run if candidate is adopted later.

Acceptance:

- candidate adoption control clearly says Safe Apply required;
- no direct apply button.

---

## PFG-25 — Stage Matrix and Route Matrix UI

Goal: advanced collapsible controls.

Tasks:

- Stage rows with mode/model/reason.
- Route rows with change class/route/default model hints.
- Warnings for unsafe changes.

Acceptance:

- hidden by default behind Advanced;
- user can understand current mode quickly.

---

## PFG-26 — Loadouts UI and persistence

Goal: simple presets for normal use.

Initial loadouts:

```text
Local Safe
Local Fast
Local Deep
Hybrid Balanced
OpenRouter Review
Greenfield Builder
Repair Specialist
```

Acceptance:

- loadout switch updates stage/provider policy;
- risky policy changes require explicit confirmation.

---

## PFG-27 — Portal Run Forge Trace metadata

Goal: attach Forge provenance to Portal runs.

Tasks:

- Add optional ForgeTrace schema to Portal run records.
- Show compact trace in Portal run sheet.
- Preserve existing Portal runs with no trace.

Acceptance:

- legacy Portal records still load;
- Forge trace is optional and sidecar-safe.

---

## PFG-28 — Portal evidence to Candidate Evaluator

Goal: use real runtime evidence.

Tasks:

- Feed Portal preview/log/save/discard/snapshot outcomes into evaluator/profile updater.
- Treat user decisions as weak feedback unless paired with runtime evidence.

Acceptance:

- runtime failure lowers candidate result;
- user discard alone does not prove model failure.

---

## PFG-29 — Capsule Forge metadata and replay

Goal: make Capsules model-aware.

Tasks:

- Add Forge projection to Capsule manifest or sidecar metadata.
- Add replay evidence linking Portal run to model profile update.
- Preserve data-free export.

Acceptance:

- package ZIP immutability preserved;
- replay can record success/failure without source mutation.

---

## PFG-30 — Real local-model Quick preset run

Goal: first real model evidence.

Tasks:

- Use configured local or self-hosted provider if available.
- Run Quick preset through normal Forge provider interface.
- Record unavailable if no model is configured.

Acceptance:

- real model output required for pass when environment is available;
- unavailable is truthful when not available.

---

## PFG-31 — Real Web App / Portal run preset

Goal: web app artifact reaches Portal.

Tasks:

- Generate/evaluate Web App task candidate.
- Apply only through Proposal/Safe Apply if adopting.
- Run in Portal and record preview/log evidence.

Acceptance:

- Portal run succeeds or failure is recorded;
- profile update uses Portal evidence.

---

## PFG-32 — Real Repair preset run

Goal: prove repair-specialist model/routing.

Tasks:

- Use a reproducible failing fixture.
- Run repair candidates.
- Verify fixed behavior.

Acceptance:

- repair success based on tests/runtime, not model claim.

---

## PFG-33 — Real Greenfield Capsule replay run

Goal: complete Portal x Forge loop.

Tasks:

- Generate or use a Greenfield artifact.
- Run through Portal.
- Save/snapshot/discard as appropriate.
- Build Capsule.
- Replay Capsule.
- Feed replay evidence into Forge profile.

Acceptance:

- at least one runnable Capsule with Forge trace exists;
- replay result updates model profile.

---

## PFG-34 — Optional OpenRouter live smoke gate

Goal: prove live OpenRouter only when explicitly available.

Tasks:

- Add opt-in live smoke command/test.
- Require env flag and API key.
- Record model ID, latency, usage, no secret.

Acceptance:

- CI passes without key;
- live unavailable is not passed;
- if run, evidence is exact.

---

## PFG-35 — Stage shadow evidence

Goal: compare legacy vs Forge for selected stages.

Stages:

```text
patch_generation
test_generation
failure_classification
repair
```

Acceptance:

- side-by-side outputs/scores recorded;
- no cutover yet;
- regressions block promotion.

---

## PFG-36 — Controlled Forge primary cutover for selected stage

Goal: promote one low-risk stage.

Tasks:

- Choose stage with best evidence.
- Enable Forge primary with legacy fallback.
- Add rollback control.

Acceptance:

- rollback tested;
- affected tests pass;
- status records exact evidence.

---

## PFG-37 — Legacy retirement gates and consumer registry

Goal: prepare deletion without deleting too early.

Tasks:

- Build consumer registry for model execution paths.
- Record remaining direct legacy callers.
- Add retirement checklist.

Acceptance:

- no deletion unless consumer-zero and benchmark gates pass.

---

## PFG-38 — Final milestone benchmark and docs

Goal: close program.

Tasks:

- Run milestone suite.
- Run real local-model preset evidence where available.
- Run Portal replay evidence.
- Run optional OpenRouter smoke only if configured.
- Update user docs.

Acceptance:

- current status marks all required packages acceptance_complete;
- no false claims;
- UI is modern and usable;
- AGENTS.md remains accurate.
