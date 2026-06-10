# Atlas Project Intelligence — Current Status

> Mutable execution checkpoint for Codex goal mode.
> Update after every work package.
> Do not infer completion from design documents or old PDT status.

## Program status

- Overall: **ACTIVE — NOT COMPLETE**
- Completed foundation: Project Digital Twin Core v1, PDT-0 through PDT-14
- Active canonical goal: `docs/atlas_project_intelligence_master_goal.md`
- Architecture: `docs/atlas_project_intelligence_architecture.md`
- Detailed design: `docs/atlas_project_intelligence_detailed_design.md`
- Public contracts: `docs/atlas_project_intelligence_contracts.md`
- Detailed implementation plan: `docs/atlas_project_intelligence_implementation_plan.md`
- Test plan: `docs/atlas_project_intelligence_test_plan.md`
- Migration/reorganization plan: `docs/atlas_project_intelligence_migration_plan.md`
- Agent entrypoint: `docs/atlas_project_intelligence_agent_entrypoint.md`
- Current work package: `PI-20` (PI-0..PI-19 completed; Milestone E done)
- Next action: Greenfield bootstrap orchestrator (PI-20)
- Blocker: none recorded
- Safety posture: existing Atlas authority, approval, Safe Apply, rollback, retry, command, project-isolation, and truthful-verification rules remain unchanged

## Important interpretation

The old `docs/atlas_project_digital_twin_current_status.md` records completion of PDT Core v1 only. It is a historical checkpoint and is not the active overall goal.

Current gaps include:

- production use of Digital Twin in real Planner/Generator/Verification paths;
- deep semantic/call/control-flow/data-flow/state/event/resource/runtime graphs;
- Architecture Blueprint Module;
- Convergence Module;
- Greenfield generation with build/run evidence;
- existing project-analysis/context/impact duplication consolidation;
- phased rollout and final comparative benchmark.

## Work package table

| WP | Title | Status | Evidence / Notes |
|---|---|---|---|
| PI-0 | Production baseline and consumer map | Completed | maps + `tests/test_project_intelligence_baseline.py` → 46 passed; twin baseline 21 passed; full twin+PI suites 171 passed |
| PI-1 | Module facade contracts and boundary tests | Completed | 4 module facades + contracts; `tests/test_project_intelligence_contracts.py`+`_boundaries.py` → 28 passed; affected suite 199 passed |
| PI-2 | Persistence and migration foundation | Completed | isolated SQLite stores (blueprint/convergence/PI) + migrations; `tests/test_project_intelligence_persistence.py` → 12 passed; affected 107 passed |
| PI-3 | Composition root and rollout model | Completed | factory/coordinator/rollout/telemetry; `tests/test_project_intelligence_rollout.py` → 27 passed (with boundaries); full PI suite 120 passed |
| PI-4 | Project identity, mode detection, lifecycle | Completed | identity/mode/lifecycle/jobs; `tests/test_project_intelligence_lifecycle.py` → 14 passed; full PI suite 134 passed |
| PI-5 | Canonical event bridge and trace expansion | Completed | event_bridge delivery trace; `tests/test_project_intelligence_event_bridge.py` → 8 passed; PI+intent_trace+baseline 147 passed |
| PI-6 | Static and semantic graph v2 | Completed | analyzers(py/js/ts-vue)+semantic graph+LSP fallback; `tests/test_project_intelligence_semantic_graph.py` → 13 passed; PI+static_graph+baseline 163 passed |
| PI-7 | Behavioral graph v2 | Completed | behavioral analyzer+graph (control-flow/side-effect/route/state/recovery/UI); `tests/test_project_intelligence_behavioral_graph.py` → 9 passed; PI+behavioral+baseline 168 passed |
| PI-8 | Runtime intelligence and reconciliation v2 | Completed | collectors+reconciliation+rollup; `tests/test_project_intelligence_runtime.py` → 9 passed; PI+reconciliation+collectors+baseline 185 passed |
| PI-9 | Context, path, impact, test selection v2 | Completed | impact/path/test-select+bounded context package; `tests/test_project_intelligence_query_context.py` → 10 passed; PI+analysis+context_broker+baseline 194 passed |
| PI-10 | Blueprint model, store, lifecycle | Completed | lifecycle+module(state machine/scopes/diff/authority/planned-ref guard)+store set_head; `tests/test_project_intelligence_blueprint_lifecycle.py` → 9 passed; PI+baseline 192 passed |
| PI-11 | Blueprint generation, review, validation | Completed | validator+generator (coverage/manifest/cycle/exec-contract/vague); `tests/test_project_intelligence_blueprint_generation.py` → 8 passed; PI+baseline 200 passed |
| PI-12 | Blueprint-to-Actual mapping hints | Completed | mapping.py (materialized/realized/blocked, evidence-gated verify, public snapshot, decoupled); `tests/test_project_intelligence_blueprint_mapping.py` → 5 passed; PI+baseline 205 passed |
| PI-13 | Convergence matcher and evaluator | Completed | matcher+evaluator (8 distinct states, file≠verified, stale guard); `tests/test_project_intelligence_convergence_eval.py` → 7 passed; PI+baseline 212 passed |
| PI-14 | Convergence decision and incremental evaluation | Completed | policy(7 actions)+incremental_evaluate; `tests/test_project_intelligence_convergence_decision.py` → 10 passed; PI+baseline 222 passed |
| PI-15 | Completion and requirement-evidence integration | Completed | completion gates+delivery-path+off fallback; `tests/test_project_intelligence_completion.py` → 8 passed; PI+baseline 230 passed |
| PI-16 | Planning envelope and Plan Compiler | Completed | plan_compiler (deterministic order, create/modify/repair, completed preserved, downstream replan, PlanPool refs); `tests/test_project_intelligence_plan_compiler.py` → 7 passed; PI+baseline 237 passed |
| PI-17 | Planner production integration | Completed | AtlasPlannerBridge (off=legacy/shadow=unchanged+telemetry/active=manifest-backed, readiness explicit, no store); `tests/test_project_intelligence_planner_bridge.py` → 5 passed; PI+baseline 242 passed |
| PI-18 | Generator and repair integration | Completed | AtlasGeneratorBridge (stale block/refresh, planned≠real, manifest in proposal, bounded repair); `tests/test_project_intelligence_generator_bridge.py` → 7 passed; PI+baseline 249 passed |
| PI-19 | Verification, checkpoint, resume | Completed | checkpoint+AtlasVerificationBridge (auto-ingest, post-verif convergence, exact-revision resume, external-change detect, idempotent replay, rollback); `tests/test_project_intelligence_verification_resume.py` → 7 passed; PI+baseline 256 passed |
| PI-20 | Greenfield bootstrap orchestrator | In Progress | current package |
| PI-21 | Coherent multi-file generation | Not Started | |
| PI-22 | Greenfield build/run/test and real E2E | Not Started | |
| PI-23 | Capability consolidation and consumer cutover | Not Started | |
| PI-24 | Cross-platform, scale, storage, rollout hardening | Not Started | |
| PI-25 | Final benchmark and legacy retirement | Not Started | |

## Per-package update template

After each package, append or update:

```text
Work package:
Status:
Commit/PR:
Changed modules/files:
Executed commands and exact results:
Unavailable checks:
Safety invariants checked:
Migration/rollout state:
Known limitations:
Next package:
Blocker, if any:
```

## Executed package log

```text
Work package: PI-19 — Verification, checkpoint, and resume integration (Milestone E complete)
Status: Completed
Commit/PR: local branch pi-19-verification-resume (not pushed/merged yet)
Changed modules/files:
- agent/project_intelligence/checkpoint.py (new) — Checkpoint (8 fields) + CheckpointController
  (immutable, idempotent save; load_latest; external-change detection; resume_decision).
- agent/project_intelligence/adapters/atlas_verification.py (new) — AtlasVerificationBridge.
- tests/test_project_intelligence_verification_resume.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- record_verification ingests runtime observations (PI-8 truthful rollup; unavailable never
  success), records last successful evidence, requests post-verification Convergence, and
  persists an idempotent checkpoint capturing requirement/Blueprint/Actual-Twin/Convergence/
  PlanPool revisions + current item + evidence + rollout mode + working-tree hash.
- Replay with the same idempotency key is a no-op (duplicate=True, convergence not re-run) —
  no duplicate apply/verification. Rollback base revision always available in the outcome.
- resume() loads the latest checkpoint after restart and resumes from exact revisions; an
  external source change (twin revision or working-tree hash differs) -> REFRESH_NEEDED before
  continuation. Checkpoints are project-isolated.
Executed commands and exact results:
- python -m py_compile (2 files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_verification_resume.py -> 7 passed in 0.67s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 256 passed in 9.81s
Unavailable checks: none required.
Safety invariants checked: unavailable != success; idempotent replay (no duplicate apply/
  verify); external change detected before continuation; rollback preserved; project isolation;
  canonical verification authority not replaced (advisory rollup + checkpoint only).
Migration/rollout state: verification/resume loop closed behind the rollout flag.
Known limitations: post-verification Convergence is requested (flag) and run by the caller via
  the PI-13/14 modules; the checkpoint store is a dedicated SQLite table (internal adapter).
Milestone: Milestone E (Atlas planning/generation/verification/recovery integration, PI-16..PI-19)
  COMPLETE.
Next package: PI-20 — Greenfield bootstrap orchestrator (Milestone F).
Blocker: none.
```

```text
Work package: PI-18 — Generator and repair production integration
Status: Completed
Commit/PR: local branch pi-18-generator-integration (not pushed/merged yet)
Changed modules/files:
- agent/project_intelligence/adapters/atlas_generation.py (new) — AtlasGeneratorBridge.
- tests/test_project_intelligence_generator_bridge.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- build_generation_context over the coordinator: off -> legacy; shadow -> legacy unchanged;
  active -> manifest-backed generation context. A stale Actual revision (base != current
  actual) BLOCKS and requests a refresh before generation.
- Planned Blueprint contracts are labelled planned=True and kept separate from actual_symbols
  (real twin symbols), so imaginary/planned symbols are never presented as real.
- proposal_metadata() exposes the context_manifest_id + base_revision for the Proposal to store.
- build_repair_context drives repair from actual failure evidence (failed observations only)
  and a bounded decision action; a non-bounded action is rejected -> halt_unsafe (never auto-exec).
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/adapters/atlas_generation.py + test -> compile OK
- python -m pytest -q tests/test_project_intelligence_generator_bridge.py -> 7 passed in 0.71s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 249 passed in 9.44s
Unavailable checks: none required.
Safety invariants checked: stale actual blocks generation; planned != real symbols; manifest
  attached to proposal; repair is evidence-driven and bounded (never auto-execution); no store
  exposed to the generator.
Migration/rollout state: generator/repair bridge ready behind the rollout flag; adopted by the
  real AtlasPatchProposalService/repair call sites without removing the legacy path.
Known limitations: active sections come from the disabled-twin stub until full active rollout;
  multi-file coherence relies on the Blueprint contracts + plan compiler ordering (PI-16).
Next package: PI-19 — Verification, checkpoint, and resume integration.
Blocker: none.
```

```text
Work package: PI-17 — Planner production integration
Status: Completed
Commit/PR: local branch pi-17-planner-integration (not pushed/merged yet)
Changed modules/files:
- agent/project_intelligence/adapters/__init__.py, atlas_planning.py (new) — AtlasPlannerBridge.
- tests/test_project_intelligence_planner_bridge.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- AtlasPlannerBridge.build_planner_context wraps the PI-3 coordinator's prepare_planning_context:
  off -> legacy context only (Intelligence not consulted as input); shadow -> legacy context
  unchanged + a side shadow artifact + recorded comparison telemetry; active -> manifest-backed
  Intelligence context layered over legacy (source=project_intelligence, manifest id, requirements/
  impacted/gaps). Twin readiness and staleness surfaced explicitly in every result.
- The bridge is an Atlas integration adapter (outside the portable cores); it holds only the
  coordinator and exposes no module store (planner never touches stores) — asserted.
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/adapters/atlas_planning.py + test -> compile OK
- python -m pytest -q tests/test_project_intelligence_planner_bridge.py -> 5 passed in 0.69s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 242 passed in 9.30s
Unavailable checks: none required.
Safety invariants checked: off=legacy unchanged; shadow does not change planner input; active
  manifest-backed; readiness/stale explicit; planner does not access module stores.
Migration/rollout state: planner bridge ready; the real Atlas planner call site adopts it behind
  the rollout flag (no legacy path removed). Active context is still backed by the disabled twin
  stub until production twin wiring (full active rollout) is enabled.
Known limitations: active context currently layers the disabled-twin package (empty sections)
  over legacy; once the rollout flag enables the real twin, sections populate without bridge changes.
Next package: PI-18 — Generator and repair production integration.
Blocker: none.
```

```text
Work package: PI-16 — Planning envelope and Blueprint Plan Compiler (Milestone E begins)
Status: Completed
Commit/PR: local branch pi-16-plan-compiler (not pushed/merged yet)
Changed modules/files:
- agent/project_intelligence/plan_compiler.py (new) — compile_plan, requirement coverage,
  PlanPool metadata + legacy loader.
- tests/test_project_intelligence_plan_compiler.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Phases architecture/delivery/repair from project mode. Deterministic item order from the
  Blueprint dependency graph (topological). Item kinds: greenfield -> create_file/
  create_structure; existing -> modify; repair -> repair.
- Completed items are preserved (status completed), never recreated. Downstream-only replan
  (replan_scope) recompiles only in-scope elements; out-of-scope items are preserved; completed
  items stay completed.
- Complete requirement + Blueprint element mappings (every element -> item; coverage helper).
- PlanPool metadata records blueprint/actual-twin/convergence/context-manifest refs (ADR-PI-012);
  load_plan_pool_metadata fills defaults so old PlanPools load cleanly.
- Deterministic code owns identity/order/mapping; LLM grouping is an optional overlay (ADR-PI-008).
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/plan_compiler.py + test -> compile OK
- python -m pytest -q tests/test_project_intelligence_plan_compiler.py -> 7 passed in 0.58s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 237 passed in 8.77s
Unavailable checks: none required.
Safety invariants checked: completed items not recreated; deterministic identity bookkeeping;
  PlanPool refs recorded; legacy PlanPool compatibility; no PlanPool/workspace mutation (compiler
  produces specs, does not write PlanPool — that is the Planner's authority in PI-17).
Migration/rollout state: plan compilation ready; wiring into the real Planner path is PI-17.
Known limitations: the compiler emits PlanItem specs; persisting to the canonical PlanPool and
  shadow comparison happen in PI-17 via the Atlas planner bridge.
Next package: PI-17 — Planner production integration.
Blocker: none.
```

```text
Work package: PI-15 — Final completion and requirement-evidence integration (Milestone D complete)
Status: Completed
Commit/PR: local branch pi-15-completion-evidence (not pushed/merged yet)
Changed modules/files:
- agent/project_intelligence/completion.py (new) — evaluate_completion gates + per-requirement
  delivery; off-mode legacy fallback.
- tests/test_project_intelligence_completion.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Eight completion gates: mandatory requirement coverage (verified), zero mandatory Blueprint
  gaps, zero unresolved decisions, zero failed verification, zero stale mandatory evidence,
  no unsafe halt, no unavailable required evidence, delivery path for every mandatory
  requirement. complete = all gates pass.
- Integrates the PI-5 delivery trace (path must reach verification/evidence per mandatory
  requirement), PI-8 runtime rollup counts (failed/unavailable), and PI-13 convergence states.
- Does NOT replace canonical verification authority: advisory only, never marks passed,
  unavailable stays incomplete; in off mode it defers to the legacy rollup result.
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/completion.py + test -> compile OK
- python -m pytest -q tests/test_project_intelligence_completion.py -> 8 passed in 0.71s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 230 passed in 8.40s
Unavailable checks: none required (rollup counts supplied by PI-8 in production).
Safety invariants checked: false-success fails rollup; unavailable remains incomplete; stale
  cannot complete; unsafe halt blocks; canonical verification authority not replaced; off mode
  uses legacy rollup.
Migration/rollout state: completion gate complete; wiring into the real Atlas final-rollup
  call site is PI-19; until then it is an advisory evaluator.
Known limitations: requirement_elements + delivery_terminal_kinds are supplied by the caller
  (the Atlas adapters wire PI-5/PI-8/PI-13 outputs in PI-17..PI-19).
Milestone: Milestone D (Convergence Module, PI-13..PI-15) COMPLETE.
Next package: PI-16 — Planning envelope and Blueprint Plan Compiler (Milestone E).
Blocker: none.
```

```text
Work package: PI-14 — Convergence decision policy and incremental reevaluation
Status: Completed
Commit/PR: local branch pi-14-convergence-decision (not pushed/merged yet)
Changed modules/files:
- agent/project_convergence/policy.py (new) — deterministic decide() over all seven actions.
- agent/project_convergence/evaluator.py — affected_elements + incremental_evaluate.
- tests/test_project_intelligence_convergence_decision.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- decide(): unsafe_required -> halt_unsafe; unresolved blueprint decision ->
  request_critical_decision; target_invalid -> revise_blueprint; interface divergence ->
  replan_downstream (only the divergent element + its downstream dependents); runtime
  divergence -> repair_current_item; mandatory gaps -> continue; all mandatory verified ->
  complete. A local mismatch never triggers a whole-project redesign. Policy mutates nothing.
- incremental_evaluate(): re-evaluates only elements whose refs changed plus their downstream
  dependents, reuses prior results otherwise, and agrees with a full re-evaluation for the
  affected subset.
Executed commands and exact results:
- python -m py_compile (2 files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_convergence_decision.py -> 10 passed in 0.61s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 222 passed in 8.19s
Unavailable checks: none required.
Safety invariants checked: deterministic rules before any LLM advice; unsafe never auto-executes
  (halt_unsafe); mandatory gap prevents complete; policy does not mutate Blueprint/PlanPool/
  workspace (asserted by re-serialisation equality); incremental == full for affected.
Migration/rollout state: Convergence decision policy complete; final rollup integration is PI-15.
Known limitations: target_invalid is an explicit signal (the heuristic for "design is wrong"
  vs "implementation is wrong" is left to PI-15/PI-19 callers); LLM advice layer is a future
  optional addition after the deterministic rule.
Next package: PI-15 — Final completion and requirement-evidence integration.
Blocker: none.
```

```text
Work package: PI-13 — Deterministic matcher and multidimensional evaluator (Milestone D begins)
Status: Completed
Commit/PR: local branch pi-13-convergence-matcher (not pushed/merged yet)
Changed modules/files:
- agent/project_convergence/matcher.py (new) — match_elements over public snapshot + PI-12
  mapping hints (no Twin/Blueprint internals); reproducible.
- agent/project_convergence/evaluator.py (new) — VerificationEvidence; evaluate_element +
  evaluate_convergence producing ElementConvergenceResult and a ConvergenceReport.
- tests/test_project_intelligence_convergence_eval.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Eight distinct states: absent/partial/materialized/observed/verified/divergent/blocked/stale.
- File existence -> MATERIALIZED only (never verified); runtime passed at the current twin
  revision -> VERIFIED; passed at a different revision -> STALE (stale evidence cannot satisfy
  mandatory verification, element stays a gap); observed -> OBSERVED; failed/interface mismatch
  -> DIVERGENT; unavailable never upgrades. Mandatory unmatched -> BLOCKED; optional -> ABSENT.
- Mismatches carry dimension + explanation; evidence_refs preserved. Report aggregates
  mandatory/optional gaps, stale evidence, coverage. Pure + reproducible; public data only.
Executed commands and exact results:
- python -m py_compile (2 files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_convergence_eval.py -> 7 passed in 0.61s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 212 passed in 7.83s
Unavailable checks: none required.
Safety invariants checked: file existence != verified; unavailable != passed; stale evidence
  cannot satisfy mandatory verification; Convergence consumes public snapshots only and mutates
  nothing.
Migration/rollout state: Convergence evaluator complete behind the module; decision policy PI-14.
Known limitations: interface/data/nonfunctional dimensions are coarse (structural + runtime are
  primary); evaluator not yet persisted to the convergence store / wired to decision (PI-14).
Next package: PI-14 — Convergence decision policy and incremental reevaluation.
Blocker: none.
```

```text
Work package: PI-12 — Blueprint-to-Actual mapping hints (Milestone C complete)
Status: Completed
Commit/PR: local branch pi-12-blueprint-mapping (not pushed/merged yet)
Changed modules/files:
- agent/architecture_blueprint/mapping.py (new) — ActualEntry/snapshot_from_public,
  suggest_mappings (materialized_as/realized_by/blocked_by), confirm_mapping (evidence-gated
  verified_by), MappingSet/build_mapping_set.
- tests/test_project_intelligence_blueprint_mapping.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Mapping uses a PUBLIC Actual snapshot (list of {ref,name,kind}); the module does not import
  agent.project_twin, so Blueprint stays valid when the Twin store implementation changes
  (AST-asserted decoupling).
- Deterministic relations: exact expected_actual_ref -> materialized_as; name heuristic ->
  realized_by; mandatory unmatched -> blocked_by. All hints status=inferred.
- Heuristic mapping is never silently verified: confirm_mapping requires non-empty evidence
  and only then yields verified_by/verified.
- Every hint carries blueprint_revision_id + twin_revision_id, so mapping history follows both.
Executed commands and exact results:
- python -m py_compile agent/architecture_blueprint/mapping.py + test -> compile OK
- python -m pytest -q tests/test_project_intelligence_blueprint_mapping.py -> 5 passed in 0.58s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 205 passed in 7.55s
Unavailable checks: none required.
Safety invariants checked: no Twin-internal coupling; heuristic != verified; evidence required
  for verification; planned/actual separation preserved.
Migration/rollout state: Blueprint Module (PI-10..PI-12) complete behind its facade; no cutover.
Known limitations: name heuristic is exact-name only; diverges_from/satisfies are recorded by
  Convergence (PI-13+) with evidence, not by suggestion.
Milestone: Milestone C (Architecture Blueprint Module, PI-10..PI-12) COMPLETE.
Next package: PI-13 — Convergence deterministic matcher and multidimensional evaluator (Milestone D).
Blocker: none.
```

```text
Work package: PI-11 — Blueprint generation, review, and validation
Status: Completed
Commit/PR: local branch pi-11-blueprint-generation (not pushed/merged yet)
Changed modules/files:
- agent/architecture_blueprint/validator.py (new) — deterministic validation with stable
  machine-readable codes (requirement_uncovered, vague_plan, dependency_cycle,
  missing_file_manifest, missing_execution_contract, unresolved_decision, planned_uses_actual_ref);
  topological order + cycle detection; requirement coverage map.
- agent/architecture_blueprint/generator.py (new) — BlueprintSpec/FileSpec; decide_scope
  (greenfield->full_project, existing small change->change_set, repair->repair);
  generate_blueprint assembles concrete bp:// elements + execution contracts deterministically.
- tests/test_project_intelligence_blueprint_generation.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Greenfield Blueprint has an exact file manifest (bp:// planned refs with file:// expected
  actual targets), entrypoint + test_contract execution contracts, dependency order; validates.
- Existing small change yields a change_set (not a full redesign); validates without forcing
  execution-contract redesign.
- Vague plans (no concrete materialization target) rejected; requirement-coverage gaps and
  dependency cycles detected; validation deterministic; diagnostics machine-readable.
Executed commands and exact results:
- python -m py_compile (2 files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_blueprint_generation.py -> 8 passed in 0.60s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 200 passed in 7.01s
Unavailable checks: none required (no LLM call — generator consumes a structured spec).
Safety invariants checked: planned bp:// never an Actual ref; LLM cannot fabricate user
  decision (planner_recommendation); Blueprint reports target only, not actual status.
Migration/rollout state: generation/validation complete behind the Blueprint module; no cutover.
Known limitations: the spec is supplied structurally (the LLM that produces it is wired in
  PI-16/PI-20); interface/schema/nonfunctional dimensions are coarse; cross-file interface
  consistency checks are minimal.
Next package: PI-12 — Blueprint-to-Actual mapping hints.
Blocker: none.
```

```text
Work package: PI-10 — Blueprint model, store, and lifecycle (Milestone C begins)
Status: Completed
Commit/PR: local branch pi-10-blueprint-model (not pushed/merged yet)
Changed modules/files:
- agent/architecture_blueprint/lifecycle.py (new) — scopes, state machine + transitions,
  planned-vs-Actual ref guard, authority guards (planner vs user decision), revision diff.
- agent/architecture_blueprint/module.py (new) — ArchitectureBlueprintModuleImpl over the
  immutable store: create/revise/review/activate/get_active_revision/get_revision.
- agent/architecture_blueprint/store.py — save_revision advance_head param + activate_revision.
- agent/project_intelligence/_persistence.py — ArtifactStore.set_head (activate an existing
  revision as head; never dangles).
- tests/test_project_intelligence_blueprint_lifecycle.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Scopes full_project/change_set/repair; states proposed/reviewed/approved/active/
  materializing/satisfied/diverged/superseded/rejected with validated transitions.
- create -> proposed (head not advanced); review -> approved when valid; activate ->
  active (sets store head, supersedes prior active); revise -> immutable child (parent
  preserved). Activated content immutable (store rejects same-id different content).
- Authority: planner_decision forces planner_recommendation; user_decision requires explicit
  confirmation — an LLM path can never fabricate a user_decision.
- Planned elements must not use Actual refs (py://, file://, ...); only expected_actual_refs
  may carry actual refs (ADR-PI-001). Structural diff (added/removed/changed elements).
- Project isolation + point-in-time reads via the immutable store.
Executed commands and exact results:
- python -m py_compile (5 files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_blueprint_lifecycle.py -> 9 passed in 0.59s
- python -m pytest -q tests/test_project_intelligence_persistence.py
  tests/test_project_intelligence_blueprint_lifecycle.py -> 21 passed (PI-2 contract preserved
  after reverting advance_head default to True)
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 192 passed in 6.91s
Unavailable checks: none required.
Safety invariants checked: activated revisions immutable; LLM cannot fabricate user_decision;
  planned != actual; project isolation; no PlanPool/Safe Apply/verification touched; Blueprint
  never reports actual implementation status.
Migration/rollout state: Blueprint module concrete impl behind the facade; the disabled
  facade stub remains for the off path. No consumer cutover yet.
Known limitations: operational lifecycle status is tracked in-module (durable content is in the
  store); generation/validation of full target contracts is PI-11; mapping hints PI-12.
Next package: PI-11 — Blueprint generation, review, and validation.
Blocker: none.
```

```text
Work package: PI-9 — Context, path, impact, and test selection v2 (Milestone B complete)
Status: Completed
Commit/PR: local branch pi-9-context-impact (not pushed/merged yet)
Changed modules/files:
- agent/project_twin/query/__init__.py, impact.py, context.py, metrics.py (new)
- tests/test_project_intelligence_query_context.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- impact.py: assess_impact (direct/transitive resolved callers + candidate callers,
  affected behaviors/side effects, recommended tests, confidence, explanation); trace_path
  (directed reachability, truthful no-path); select_tests (from real runtime coverage).
- context.py: build_context_package -> TwinContextPackage with graph-neighborhood candidate
  generation, bounded traversal (max neighborhood + token budget), objective/phase relevance,
  contradiction -> uncertainties, stale labeling, source excerpts at the manifest revision,
  all sections + persisted-shaped manifest. Essential requirement/preserve items never dropped.
- metrics.py: impact precision/recall + test-recommendation precision (recorded).
Acceptance: no full graph dump (bounded); target + mandatory requirements prioritized;
  stale/contradicted labeled or excluded; source excerpts match manifest revision; package is
  portable (pure contract DTO, no Atlas schema).
Executed commands and exact results:
- python -m py_compile (4 new files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_query_context.py -> 10 passed in 0.68s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_analysis.py
  tests/test_project_twin_context_broker.py tests/test_project_twin_baseline.py
  -> 194 passed in 7.40s (Core v1 analysis + context broker unbroken)
Unavailable checks: none required.
Safety invariants checked: bounded context (no full dump); contradicted/stale never presented
  as verified fact; essential safety/requirement items preserved; portable (no FastAPI/PlanPool/
  SQLite); read-only over graphs + workspace sources.
Migration/rollout state: Digital Twin Module query/context engine complete; wiring into the
  DigitalTwinModule facade active path + production consumers is PI-16..PI-18.
Known limitations: relevance scoring is coarse (target-proximity + confidence); freshness uses
  injected stale/contradicted sets rather than per-node revision tracking; incidents/memory/
  skills/nexus sections are passed in by the caller (adapters wire them in PI-16+).
Milestone: Milestone B (Digital Twin Module production integration, PI-4..PI-9) COMPLETE.
Next package: PI-10 — Blueprint model, store, and lifecycle (Milestone C).
Blocker: none.
```

```text
Work package: PI-8 — Runtime intelligence and reconciliation v2
Status: Completed
Commit/PR: local branch pi-8-runtime-reconciliation (not pushed/merged yet)
Changed modules/files:
- agent/project_twin/runtime/__init__.py, collectors.py, reconciliation.py (new)
- tests/test_project_intelligence_runtime.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Collectors v2 normalize pytest (+coverage), Playwright, and API observations into
  RuntimeObservationRecord with result passed/failed/observed/unavailable; coverage and
  stack frames map to PI-6 symbol refs; source revision preserved.
- safe_collect turns a collector exception into a single unavailable observation (never a
  fabricated passed); unavailable_observation is explicit and non-convertible.
- reconcile(): confirm/partially_confirm (passed at current revision), contradict (failed,
  prior status retained in history -> contradicted), unavailable, stale (only stale-revision
  observations -> not verified), not_observed. A verified status requires a matching source
  revision; stale observations never verify new source.
- summarize_rollup(): success requires >=1 passed, zero failed, zero unavailable; unavailable
  is counted and forces success=False everywhere (UI + rollup).
- Collectors carry no execution authority (pure normalization/decision functions).
Executed commands and exact results:
- python -m py_compile (3 new files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_runtime.py -> 9 passed in 0.64s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_reconciliation.py
  tests/test_project_twin_runtime_collectors.py tests/test_project_twin_baseline.py
  -> 185 passed in 6.87s (Core v1 reconciliation + collectors unbroken)
Unavailable checks: real pytest/playwright runs not executed here; collectors tested on
  normalized report fixtures; unavailable path explicitly tested.
Safety invariants checked: unavailable never becomes passed (reconcile + rollup + safe_collect);
  collector failure cannot mark success; verified requires revision match; contradicted facts
  retained historically; no execution authority in collectors; no canonical store mutated.
Migration/rollout state: v2 runtime added beside Core v1 collectors/reconciliation; no cutover.
Known limitations: latency/memory and Atlas Play/DB/file/process collectors are stubs to be
  extended; coverage-to-symbol mapping assumes qualname granularity; reconciliation is a
  pure decision layer not yet persisted into the twin store (PI-9+ wiring).
Next package: PI-9 — Context, path, impact, and test selection v2.
Blocker: none.
```

```text
Work package: PI-7 — Behavioral graph v2
Status: Completed
Commit/PR: local branch pi-7-behavioral-graph (not pushed/merged yet)
Changed modules/files:
- agent/project_twin/graph/behavioral.py (new) — BehavioralGraph (facts/relations,
  inferred-only invariant, incremental invalidation).
- agent/project_twin/analyzers/behavioral.py (new) — BehavioralAnalyzer + combined traces
  (trace_request_to_persistence, trace_ui_to_api).
- tests/test_project_intelligence_behavioral_graph.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Python: per-function control-flow summary (branches/loops/returns/raises/try/finally/
  awaits); concrete side effects (file path, DB table from SQL, network URL, process) with
  recorded resources; FastAPI route decorators -> route facts handled_by the handler; self
  state mutation; retry + rollback recovery detection.
- HTTP request-to-persistence trace: route -> handler -> resolved calls (reusing PI-6
  semantic call edges) -> DB side effects/tables, queryable.
- JS UI path: ui_event (addEventListener/onX) -> api_call (fetch/axios) -> route, queryable.
- Every behavioral fact/relation is status=inferred with a derivation and confidence < 1.0;
  heuristics are never verified (false-certainty test). Behavior owners reuse the PI-6
  static refs (no duplicate identities). Unsupported constructs emit diagnostics.
Executed commands and exact results:
- python -m py_compile (2 new files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_behavioral_graph.py -> 9 passed in 0.63s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_behavioral_graph.py
  tests/test_project_twin_baseline.py -> 168 passed in 6.28s (Core v1 behavioral graph unbroken)
Unavailable checks: none required.
Safety invariants checked: pure stdlib analyzers; heuristics never verified; no canonical
  store/PlanPool/FastAPI/SQLite imported; static identities reused not duplicated.
Migration/rollout state: v2 behavioral foundation added beside Core v1 behavioral_graph;
  no cutover, no deletion.
Known limitations: data-flow propagation is coarse (control-flow summary, not full SSA);
  interprocedural propagation relies on resolved call edges only; JS UI linkage is file-level
  heuristic; runtime confirmation is PI-8.
Next package: PI-8 — Runtime intelligence and reconciliation v2.
Blocker: none.
```

```text
Work package: PI-6 — Static and semantic graph v2
Status: Completed
Commit/PR: local branch pi-6-semantic-graph (not pushed/merged yet)
Changed modules/files:
- agent/project_twin/graph/__init__.py, graph/semantic.py (new) — deterministic node/edge
  model, collision-free canonical refs, resolved vs candidate edges, incremental invalidation.
- agent/project_twin/analyzers/__init__.py, registry.py, python.py, javascript.py,
  typescript_vue.py, default.py (new) — coarse analyze op + capability/version manifest;
  Python AST semantics; JS/TS/Vue heuristic basics; CodeIntel parity helper.
- agent/project_twin/lsp_adapter.py (new) — AST fallback with recorded degradation.
- tests/test_project_intelligence_semantic_graph.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Python: module/symbol/type graph; import & module resolution; alias and re-export edges;
  inheritance + override; decorator edges; resolved call targets (local/imported/module-alias/
  self) vs may-call candidates (confidence < 1.0). Same-name functions in different modules
  are distinct refs (not collapsed).
- JS/TS/Vue: imports + top-level functions; Vue component node with template flag; heuristic
  facts carry confidence < 1.0.
- Capability/version manifest per analyzer; LSP unavailable -> AST fallback records
  lsp_unavailable_ast_fallback; old-CodeIntel parity (matched/missing/coverage) recorded;
  incremental invalidation drops only the changed file; re-analysis is idempotent.
- Core v1 static_graph.py kept unchanged (ADAPT-then-REPLACE; parity recorded, no cutover).
Executed commands and exact results:
- python -m py_compile (8 new files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_semantic_graph.py -> 13 passed in 0.58s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_static_graph.py
  tests/test_project_twin_baseline.py -> 163 passed in 5.96s (Core v1 static graph unbroken)
Unavailable checks: LSP server intentionally not spawned (probe -> unavailable); recorded
  as degradation, never claimed as LSP-quality.
Safety invariants checked: analyzers are pure (stdlib only); no FastAPI/PlanPool/SQLite;
  heuristic facts never marked verified; no canonical store touched.
Migration/rollout state: v2 semantic foundation added beside Core v1 with parity recorded;
  no consumer cutover, no legacy deletion (REPLACE gate not yet reached).
Known limitations: data-flow/control-flow and full JS/TS call resolution are PI-7+; JS/TS/Vue
  remain regex-heuristic; cross-module call resolution beyond imports is candidate-only.
Next package: PI-7 — Behavioral graph v2.
Blocker: none.
```

```text
Work package: PI-5 — Canonical event bridge and delivery trace expansion
Status: Completed
Commit/PR: local branch pi-5-event-bridge (not pushed/merged yet)
Changed modules/files:
- agent/project_twin/event_bridge.py (new) — CanonicalEventBridge + DeliveryTraceProjector
  (v2 expansion). Core v1 intent_trace.py and events.py kept unchanged (KEEP).
- tests/test_project_intelligence_event_bridge.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Consumes already-committed ProjectEventEnvelope events (full catalog) and projects a
  delivery-trace model: message -> requirement -> plan -> plan_item -> proposal ->
  applied refs -> verification -> evidence, preserving correlation/run/pool/item ids and
  apply revision on applied refs.
- At-least-once + idempotent: replaying the whole flow adds zero new nodes/edges (dedup by
  idempotency key and by ref/edge key).
- Missing links emit diagnostics and create no fabricated edge (e.g. proposal with no plan
  item -> node only + diagnostic). Unknown event types are rejected with a diagnostic.
- Projection failure marks the project degraded and enqueues an idempotent retry job; it has
  no canonical-write path, so a successful Safe Apply is never rolled back (ADR-PI-011).
- Project isolation: one project's trace never returns another project's facts.
Executed commands and exact results:
- python -m py_compile agent/project_twin/event_bridge.py + test -> compile OK
- python -m pytest -q tests/test_project_intelligence_event_bridge.py -> 8 passed in 0.71s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_intent_trace.py
  tests/test_project_twin_baseline.py -> 147 passed in 5.70s (Core v1 intent_trace unbroken)
Unavailable checks: none required.
Safety invariants checked: bridge holds no canonical store; projection never mutates
  canonical PlanPool/Conversation/verification; unavailable/failed never become passed;
  degraded+retry instead of data loss.
Migration/rollout state: delivery-trace expansion is additive; not yet wired to live Atlas
  event producers (the "selected producer adapters" land with PI-17 integration).
Known limitations: projector is in-memory (per-process); durable backing + reconciliation
  with the static graph is later (PI-8). memory/skill/nexus events are still projected by
  the Core v1 adapters, not this bridge.
Next package: PI-6 — Static and semantic graph v2.
Blocker: none.
```

```text
Work package: PI-4 — Project identity, mode detection, and lifecycle
Status: Completed
Commit/PR: local branch pi-0-production-baseline (not pushed/merged)
Changed modules/files:
- agent/project_twin/project_identity.py (new) — stable project_id + separate workspace_id
  (worktree isolation), read-only git probe with path fallback, deterministic working-tree hash.
- agent/project_intelligence/project_mode.py (new) — empty/greenfield_partial/existing/
  generated_unverified/imported_unknown detection; git/docs/metadata ignored per contract §6.1.
- agent/project_twin/lifecycle.py (new) — readiness (absent/building/ready/stale/degraded/
  corrupt/disabled), parser-version + source-revision + working-tree stale detection, and the
  full-build vs incremental-refresh decision; corrupt fails closed.
- agent/project_twin/jobs.py (new) — ProjectionJobService over an injected JobStore (the PI
  job journal): schedule, startup recovery, bounded-retry run with never-mark-done-on-error.
- tests/test_project_intelligence_lifecycle.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Empty directory yields a valid repository-level identity; distinct working dirs get distinct
  project ids (no worktree leakage); explicit workspace/sandbox id honoured.
- External edits change the working-tree hash -> STALE -> incremental refresh; parser-version
  change -> STALE; corrupt integrity -> CORRUPT -> full rebuild (fails closed).
- Projection jobs resume after restart (running -> requeued) and retry within bounds, failing
  explicitly rather than fabricating completion (ADR-PI-013).
Executed commands and exact results:
- python -m py_compile (4 new files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_lifecycle.py -> 14 passed in 2.47s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 134 passed in 4.94s
Unavailable checks: git probe returns None when git/repo absent (path fallback) — not an error.
Safety invariants checked: read-only inspection; project/workspace isolation enforced in
  identity; no PlanPool/approval/Safe Apply/rollback/command/verification behavior touched;
  twin core does not import a concrete Atlas store (JobStore injected).
Migration/rollout state: lifecycle primitives ready; not yet wired into the coordinator's
  active path (that wiring lands with PI-5 event bridge and PI-17 integration).
Known limitations: lifecycle build/refresh decisions are computed but the real graph build is
  PI-6+. run_one retry uses a coarse project-level requeue (single-job runner model).
Next package: PI-5 — Canonical event bridge and delivery trace expansion.
Blocker: none.
```

```text
Work package: PI-3 — Composition root and rollout model
Status: Completed
Commit/PR: local branch pi-0-production-baseline (not pushed/merged)
Changed modules/files:
- agent/project_intelligence/rollout.py (new) — RolloutConfig (off/shadow/active, per-phase
  gating, deterministic parsing, legacy CODEAGENT_PROJECT_TWIN_* compatibility mapping).
- agent/project_intelligence/telemetry.py (new) — side-effect-free TelemetrySink + shadow
  comparison artifacts.
- agent/project_intelligence/coordinator.py (new) — ProjectIntelligenceCoordinator: rollout
  -aware facade; off==baseline (no persistence), shadow computes+records only, active wired
  through module facades.
- agent/project_intelligence/factory.py (new) — build_project_intelligence composition root
  with dependency injection.
- tests/test_project_intelligence_rollout.py (new); tests/test_project_intelligence_boundaries.py
  (scan the 4 new portable cores for forbidden imports).
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Off mode behaviourally equivalent to baseline: returns baseline packages, no telemetry,
  no persistence touched.
- Shadow mode returns the baseline package (Planner/Generator inputs unchanged) and records
  exactly one shadow_comparison telemetry artifact per call (ADR-PI-017).
- Active mode tags the manifest active and wires through the twin facade; apply requests a
  refresh; never an execution authority; unavailable never becomes passed.
- Deterministic config parsing; unknown phases dropped; legacy twin env vars map in when the
  new vars are unset; new vars take precedence.
- Coordinator depends only on facades + telemetry (no store/connection) — tested.
Executed commands and exact results:
- python -m py_compile (4 new files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_rollout.py
  tests/test_project_intelligence_boundaries.py -> 27 passed in 1.13s
- python -m pytest -q tests/test_project_intelligence_*.py tests/test_project_twin_baseline.py
  -> 120 passed in 2.84s
Unavailable checks: none required.
Safety invariants checked: off path unchanged; rollback to legacy immediate (flag off);
  no PlanPool/approval/Safe Apply/rollback/retry/command/isolation/verification behavior
  touched; coordinator holds no private store; boundary test rejects forbidden imports.
Migration/rollout state: composition root + rollout model in place, disabled by default.
Known limitations: active mode still yields disabled twin content until PI-4+ wires the real
  Digital Twin lifecycle/graph. Coordinator not yet wired into real Atlas Planner/Generator
  call sites (PI-17/PI-18).
Next package: PI-4 — Project identity, mode detection, and lifecycle.
Blocker: none.
```

```text
Work package: PI-2 — Persistence and migration foundation
Status: Completed
Commit/PR: local branch pi-0-production-baseline (not pushed/merged)
Changed modules/files:
- agent/project_intelligence/_persistence.py (new) — shared, dependency-neutral SQLite
  kernel: connection factory, transactional/repeatable migration runner, generic immutable
  revisioned ArtifactStore (idempotency, stale-parent rejection, point-in-time, integrity).
- agent/architecture_blueprint/migrations.py, store.py (new) — immutable Blueprint revisions.
- agent/project_convergence/migrations.py, store.py (new) — immutable Convergence report history.
- agent/project_intelligence/migrations.py, store.py (new) — immutable Context Manifests +
  restart-safe job journal (enqueue/claim/complete/recover, ADR-PI-011).
- tests/test_project_intelligence_persistence.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Each module owns an isolated SQLite store behind its facade; SQLite stays an internal
  adapter (ADR-PI-015) — no public contract imports it (boundary test unchanged).
- Immutable revision rows; one put == one transaction with rollback; duplicate idempotency
  key is a harmless no-op; stale expected-parent is rejected; project/workspace isolation;
  point-in-time reads; integrity check returns ok/corrupt with diagnostics.
- Migrations are repeatable (IF NOT EXISTS + version guard) and rollback-safe (per-migration
  BEGIN/COMMIT/ROLLBACK; a failed migration is not recorded).
- No PlanPool/Conversation/Nexus/Memory canonical data is migrated or rewritten (ADR-PI-004).
Executed commands and exact results:
- python -m py_compile (7 new module files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_persistence.py -> 12 passed in 0.63s
- python -m pytest -q boundaries+contracts+persistence+baseline+twin_baseline -> 107 passed in 2.45s
Unavailable checks: none required (in-memory + temp SQLite only).
Safety invariants checked: stores are advisory persistence; no workflow/PlanPool/approval/
  Safe Apply/rollback/retry/command/isolation/verification behavior touched; SQLite not
  exposed through any facade.
Migration/rollout state: persistence introduced; not yet wired to facades (PI-3 composition).
Known limitations: stores are standalone; the facades still return disabled results until
  PI-3 composition root + rollout wire them behind the rollout flag.
Next package: PI-3 — Composition root and rollout model.
Blocker: none.
```

```text
Work package: PI-1 — Module facade contracts and boundary tests
Status: Completed
Commit/PR: local branch pi-0-production-baseline (not pushed/merged)
Changed modules/files:
- agent/project_intelligence/__init__.py, contracts.py, facade.py (new)
- agent/project_twin/facade.py (new; atlas.digital_twin.v2 facade over Core v1)
- agent/architecture_blueprint/__init__.py, contracts.py, facade.py (new)
- agent/project_convergence/__init__.py, contracts.py, facade.py (new)
- tests/test_project_intelligence_contracts.py, tests/test_project_intelligence_boundaries.py (new)
- tests/test_project_intelligence_baseline.py (PI-0 absence pin flipped to presence pin)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Versioned public contracts for four families: atlas.project_intelligence.v1,
  atlas.digital_twin.v2, atlas.architecture_blueprint.v1, atlas.project_convergence.v1.
- Four coarse-grained facade Protocols (DigitalTwinModule, ArchitectureBlueprintModule,
  ConvergenceModule, ProjectIntelligenceModule) + shared contract kernel (ProjectIdentity,
  ContextManifest, ContextItem, SourceExcerpt, RuntimeObservationRecord, ProjectMode,
  typed IntelligenceErrorCode/IntelligenceError).
- Disabled-by-default concrete stubs for all four facades: explicit DISABLED/unavailable
  results; never fabricate twin revisions, blueprints, convergence completion, or passed
  observations; unavailable observations stay unavailable (ADR-PI-013); blueprint
  activate/get_revision raise typed errors instead of fabricating a revision.
- v1 compatibility readers: accepts_twin_contract_version (reads atlas.project_twin.v1
  and v2); context_item_from_v1_slice_item adapts a Core v1 context item without upgrading
  status/confidence.
- Dependency direction enforced: PI facade -> twin/blueprint/convergence facades; twin and
  blueprint independent; portable cores import only stdlib/typing/pydantic + shared kernel.
  PI package __init__ exports the coordinator lazily (PEP 562) to keep the kernel import
  cycle-free.
Executed commands and exact results:
- python -m py_compile (10 new module files + 2 new tests) -> compile OK
- python -m pytest -q tests/test_project_intelligence_contracts.py
  tests/test_project_intelligence_boundaries.py -> 28 passed in 1.06s
- python -m pytest -q tests/test_project_intelligence_baseline.py + contracts + boundaries
  + tests/test_project_twin_*.py -> 199 passed in 7.30s
Unavailable checks: none required (no runtime/browser instrumentation in PI-1).
Safety invariants checked: facades are advisory/disabled; no PlanPool/approval/Safe Apply/
  rollback/retry/command/isolation/verification behavior touched; no facade exposes a private
  store; no portable core imports FastAPI/app.api/PlanPool/SQLite (AST boundary test).
Migration/rollout state: facades introduced disabled; no consumer cutover; no legacy deletion.
Known limitations: facades are stubs — open/refresh/query/build_context/create/evaluate
  return disabled results. Real persistence (PI-2), composition/rollout (PI-3) and Digital
  Twin production wiring (PI-4+) are later packages.
Next package: PI-2 — Persistence and migration foundation.
Blocker: none.
```

```text
Work package: PI-0 — Production baseline and consumer map
Status: Completed
Commit/PR: local branch pi-0-production-baseline (not pushed/merged)
Changed modules/files:
- docs/atlas_project_intelligence_existing_capability_map.md (new)
- docs/atlas_project_intelligence_consumer_map.md (new)
- docs/atlas_project_intelligence_migration_matrix.md (new)
- tests/test_project_intelligence_baseline.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Read-only executable baseline of project-analysis/context/impact/verification-support
  and Project Twin Core v1 capabilities against current main (HEAD 0fd98c1).
- existing_capability_map: owners by symbol, duplication, reusable contracts, missing
  behavior, migration risk (capability inventory §4; duplication §6).
- consumer_map: direct consumers by symbol for every owner; recorded that the Twin Core v1
  has exactly one production consumer today (app/api/project_twin.py, read-only) — the
  central production-wiring gap; pipeline + repo_context APIs are the principal orchestrators.
- migration_matrix: validated + expanded migration_plan §4; KEEP/ADAPT/REPLACE/REMOVE for
  every owner + net-new modules, with PI destination and retirement gate per row.
- baseline test pins: owner importability + owner symbols present; deterministic CodeIntel
  symbol/dependency output; Code Explorer duplication present; HybridMemory long-scope
  no-op without saver; Twin Core v1 contracts (atlas.project_twin.v1) present; ABSENCE of
  the four PI module packages (PI-1 introduces them); PDT Core v1 recorded complete and
  the PI program recorded ACTIVE at PI-0.
Executed commands and exact results:
- python -m py_compile tests/test_project_intelligence_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_baseline.py -> 46 passed in 0.85s
- python -m pytest -q tests/test_project_twin_baseline.py -> 21 passed in 0.84s
- python -m pytest -q tests/test_project_twin_*.py tests/test_project_intelligence_baseline.py
  -> 171 passed in 6.96s
Unavailable checks: none required for PI-0 (no runtime/browser instrumentation involved).
Safety invariants checked: no production code changed; no workflow/PlanPool/approval/
  Safe Apply/rollback/retry/command-allowlist/isolation/verification behavior touched
  (docs + read-only test only).
Migration/rollout state: classification recorded; no cutover, no deletion, no rollout change.
Known limitations: maps are descriptive; the four module facades do not exist yet (PI-1).
Next package: PI-1 — Module facade contracts and boundary tests.
Blocker: none.
```

## Completion rule

Do not mark the program COMPLETE until PI-25 and all final Definition of Done conditions pass. Individual modules may be complete earlier, but production integration, real E2E, reorganization, rollout, and comparative benchmark are mandatory parts of the goal.
