# Atlas Project Intelligence Recovery — Implementation Plan

Status: canonical sequential implementation plan.

The active sequence is `PIR-0` through `PIR-15`. Execute in order. A package may be marked complete only after its acceptance level passes; focused unit tests alone are insufficient for packages requiring production or live evidence.

## Status vocabulary

```text
not_started
in_progress
component_complete
production_connected
acceptance_complete
blocked
```

Only `acceptance_complete` advances the canonical current package unless the plan explicitly allows a later live-evidence phase.

## Milestones

| Milestone | Packages | Goal |
|---|---|---|
| R-A | PIR-0..PIR-2 | truthful baseline, durable concrete modules, production composition |
| R-B | PIR-3..PIR-5 | real Twin lifecycle/event/runtime/query loop |
| R-C | PIR-6..PIR-7 | deep semantic/behavior/data-flow intelligence |
| R-D | PIR-8..PIR-9 | durable Blueprint and Convergence correctness |
| R-E | PIR-10..PIR-12 | real Atlas planning/generation/apply/verification/recovery integration |
| R-F | PIR-13 | real Greenfield state machine and E2E |
| R-G | PIR-14..PIR-15 | rollout, platform/scale evidence, comparative benchmark, retirement |

---

## PIR-0 — Truthful baseline, executable inventory, and regression locks

### Goal

Replace completion-by-document with an executable, current baseline of real consumers, concrete implementations, production imports, and known defects.

### Required changes

1. Add `tests/test_project_intelligence_recovery_baseline.py`.
2. Add a source-based consumer inventory generator under `tools/` or `agent/project_intelligence/inspection/`.
3. Enumerate:
   - production Atlas entrypoints;
   - legacy analysis/context/impact/test/trace/runtime consumers;
   - Project Intelligence facade/adapters;
   - actual imports and construction sites;
   - disabled versus concrete modules;
   - current database defaults and durability.
4. Encode critical defects as failing regression tests before fixing:
   - production factory creates disabled modules;
   - coordinator active packages are empty/baseline;
   - apply/verification are not accepted;
   - no concrete Twin/Convergence facade;
   - Blueprint status lost after reopen;
   - event projection workspace collision;
   - Convergence revision identity mismatch;
   - premature completion policy;
   - Plan Compiler cycle acceptance;
   - synthetic E2E/benchmark cannot count as live evidence.
5. Add a machine-readable inventory artifact, for example:
   `docs/generated/atlas_project_intelligence_consumer_inventory.json`.
6. Update the legacy/current status wording so PI-0..PI-25 are Foundation Track, not overall completion.

### Acceptance

- inventory is generated from current code, not manually asserted only;
- every critical finding has a reproducing test or explicit inspection assertion;
- no production behavior changes yet;
- existing test suite remains green except intentionally xfailed recovery regressions with issue codes;
- current status selects PIR-1.

### Required evidence

```text
consumer inventory command and artifact
focused baseline tests
full affected suite
exact count of production callers of each new facade
```

---

## PIR-1 — Durable concrete module foundations

### Goal

Implement real `DigitalTwinModuleImpl` and `ConvergenceModuleImpl`, repair Blueprint durability, and make all concrete modules pass public-facade conformance tests independently of Atlas.

### Required changes

#### Digital Twin

- add `agent/project_twin/module.py`;
- add durable Twin revision/graph/manifest/observation stores;
- implement public facade methods with minimal but real current PI-6..PI-9 helpers;
- key all state by `(project_id, workspace_id)`;
- use durable DB paths supplied by caller;
- retain prior active revision on refresh failure.

#### Blueprint

- persist status/review/decision history;
- make `get_active` deterministic per project/workspace;
- reconstruct state after process reopen;
- add optimistic activation checks.

#### Convergence

- add `agent/project_convergence/module.py`;
- persist mappings, reports, element results, and decisions;
- implement `evaluate`, `get_latest`, and `decide` through public contracts;
- separate source revision and Twin revision fields.

#### Contracts

- type composition dependencies as protocols, not disabled concrete classes;
- add reusable conformance tests for disabled and concrete implementations.

### Acceptance

- all four concrete/disabled facades pass contract and isolation tests;
- concrete modules can be constructed with no FastAPI/PlanPool imports;
- data survives close/reopen;
- same project with two workspace IDs cannot observe each other;
- no default production constructor uses `:memory:`;
- prior valid revision remains active after a failed refresh/evaluation transaction.

### Required tests

```text
test_project_intelligence_facade_conformance.py
test_project_twin_module_durability.py
test_blueprint_durable_lifecycle.py
test_convergence_module_durability.py
test_project_workspace_isolation.py
```

---

## PIR-2 — Production composition root, service lifecycle, and rollout preflight

### Goal

Construct and register the real Project Intelligence service in the application while preserving legacy behavior in off mode.

### Required changes

1. Add `agent/project_intelligence/production_factory.py`.
2. Add `agent/project_intelligence/service_registry.py` or equivalent app lifecycle holder.
3. Resolve durable paths from existing Atlas `ca_data_dir`.
4. Construct concrete Twin, Blueprint, Convergence, checkpoint, telemetry, rollout, and event stores.
5. Register service on application state at startup and close at shutdown.
6. Add read-only health/inspection endpoint under `app/api/atlas_project_intelligence.py`.
7. Add rollout preflight:
   - off may use disabled modules;
   - shadow/active require concrete healthy modules;
   - corrupt/unmigrated stores block promotion;
   - current phase/mode and implementation class are visible.
8. Persist rollout state and rollback history.

### Acceptance

- real app startup constructs concrete modules once;
- off mode remains behaviorally identical to legacy Atlas;
- shadow mode computes but does not alter canonical inputs;
- active mode cannot start with a disabled required module;
- service survives app restart using the same data root;
- health endpoint exposes no secrets/private store rows.

### Required tests

```text
test_project_intelligence_production_composition.py
test_project_intelligence_app_lifecycle.py
test_project_intelligence_rollout_preflight.py
test_project_intelligence_health_api.py
```

---

## PIR-3 — Real project source snapshots and Twin refresh lifecycle

### Goal

Make `open_project`, `refresh`, and `rebuild` operate on real workspaces and produce immutable durable Twin revisions.

### Required changes

1. Add workspace-safe `ProjectSourceAdapter`.
2. Resolve:
   - safe root;
   - Git base revision;
   - dirty working-tree identity;
   - working-tree hash;
   - changed paths;
   - parser manifest.
3. Implement full/incremental refresh transaction.
4. Add per-project/workspace leases and restart-safe refresh jobs.
5. Persist last-build record and readiness.
6. Validate path traversal/symlink escape, file count/size budgets, binary/ignored files.
7. Connect PI-6 semantic, PI-7 behavioral, and PI-9 query inputs through the concrete module.
8. Expose explicit stale/degraded/corrupt diagnostics.

### Acceptance

- opening a real repository creates a ready Twin revision;
- modifying one file creates a child revision and invalidates only affected file facts plus linker dependents;
- deleting/renaming files retires stale facts;
- failed analysis leaves prior active revision intact;
- restart recovers queued/running refresh work idempotently;
- dirty working tree creates a distinct source revision.

### Required acceptance repositories

- a small multi-module Python fixture;
- a JS/TS/Vue fixture;
- KasaneCore subset or full repository under bounded configuration.

---

## PIR-4 — Durable canonical event and delivery projection integration

### Goal

Connect already-committed Atlas events to a durable, workspace-isolated delivery trace and Twin refresh triggers.

### Required changes

1. Replace in-memory projector state with durable storage.
2. Key all projection state by `(project_id, workspace_id)`.
3. Persist full event payload or canonical lookup reference.
4. Implement durable inbox/outbox states and poison-event handling.
5. Add canonical emit adapters after successful:
   - requirement confirmation/revision;
   - plan/PlanItem state changes;
   - proposal state changes;
   - Safe Apply;
   - verification;
   - runtime observation;
   - Memory/Skill/Nexus events where available.
6. Trigger Twin refresh after `workspace.changed` and successful Safe Apply.
7. Preserve at-least-once/idempotent semantics through restart.
8. Add read-only delivery-trace queries.

### Acceptance

- a real PlanPool/Proposal/Safe Apply/Verification flow creates a queryable delivery path;
- duplicate replay adds no duplicate facts;
- two workspaces never collide;
- projector failure does not roll back canonical work and is retried after restart;
- missing links remain diagnostics, not fabricated edges.

---

## PIR-5 — Real verification ingestion, reconciliation, context, impact, and test selection

### Goal

Connect actual verification artifacts to durable observations and make the Twin context/query APIs useful to production consumers.

### Required changes

1. Add adapters from existing Atlas verification outputs to runtime observations.
2. Preserve per-test coverage rather than flattening all coverage onto every test.
3. Store source and Twin revisions separately.
4. Reconcile observations with exact facts and resource relations.
5. Add durable latest observation/reconciliation queries.
6. Repair context ranking:
   - objective and phase relevance;
   - graph distance across multiple relation kinds;
   - confidence/freshness/risk/evidence status;
   - preserve behavior and mandatory requirements first.
7. Use symbol source ranges for excerpts.
8. Define token-budget overflow behavior and manifest reasons.
9. Benchmark impact/test-selection precision and recall on labeled fixtures.

### Acceptance

- actual test results from the canonical verification path are ingested automatically;
- stale evidence never verifies new source;
- per-test recommendations correspond to actual coverage;
- target source excerpts point to the relevant symbol range;
- planning/generation context packages are non-empty on a real repository;
- context remains bounded and manifests are durable.

---

## PIR-6 — Whole-project semantic graph and parser-backed frontend analysis

### Goal

Raise PI-6 from file-local extraction to a real project semantic graph.

### Required changes

1. Implement a two-pass project linker.
2. Validate imports and symbols against project roots.
3. Resolve transitive aliases/re-exports with cycle guards.
4. Build cross-module type/class tables.
5. Resolve inheritance/override and Protocol/ABC candidates.
6. Infer receiver types from annotations, constructors, assignments, and parameters.
7. Emit exact calls where proven and bounded candidates otherwise.
8. Integrate LSP enrichment with explicit availability state.
9. Replace final regex-only TS/Vue path with parser-backed adapter and retain degraded fallback.
10. Persist source ranges and analyzer version/capability manifests.
11. Add real-repository precision/recall benchmark corpus.

### Acceptance

- cross-module calls, imports, overrides, and re-exports resolve on labeled fixtures;
- false resolved edges stay below the defined threshold;
- unsupported dynamics are candidates with reasons;
- parser unavailable is degraded, not silently equivalent;
- incremental refresh produces the same result as full rebuild for affected facts.

---

## PIR-7 — Real CFG, data-flow, state/event/recovery, and resource graphs

### Goal

Replace PI-7 summary heuristics with the behavioral intelligence required by the master goal.

### Required changes

1. Implement per-callable basic-block CFG.
2. Implement SSA-lite/def-use graph.
3. Connect parameters, assignments, attributes, call args, returns, predicates, and resource sinks.
4. Add bounded interprocedural propagation over resolved calls.
5. Build state transition graph from enums/literals/reducers/status assignments.
6. Build event producer/consumer relations.
7. Build retry/timeout/backoff/rollback/compensation transitions.
8. Add concrete resource identities for file, DB, API, network, process, dependency, config, UI/rendering.
9. Replace frontend all-events-to-all-APIs linking with handler-scope binding.
10. Persist graph facts with derivation/confidence/source ranges.
11. Add path/impact validation against labeled behaviors.

### Acceptance

- CFG contains branch/loop/exception/finally edges, not only counts;
- def-use paths reach expected sinks on fixtures;
- UI handler maps only to API calls in its reachable scope;
- state/retry/rollback transitions are queryable;
- request-to-persistence and UI-to-API paths match labeled expected paths;
- bounded analysis does not explode on KasaneCore.

---

## PIR-8 — Durable Blueprint planning, review, and critical-decision integration

### Goal

Make Blueprint a usable target-state authority for existing and Greenfield projects.

### Required changes

1. Expand Blueprint contracts/elements for interfaces, API/schema/data/config/dependency/runtime/NFR/preserve behavior.
2. Add `BlueprintPlannerAdapter` using Requirement + Actual context.
3. Integrate deterministic generator, validator, reviewer, and durable lifecycle.
4. Make existing-project default scope change-set; full redesign requires explicit approval.
5. Validate actual command values and command-authority compatibility.
6. Persist reviews, diagnostics, decisions, status history, and active project/workspace index.
7. Connect unresolved decisions to existing clarification/critical-decision services.
8. Add revision diff and safe activation/revision flows.

### Acceptance

- a normal existing-project request produces a scoped Change Blueprint;
- an empty project produces an exact full-project Blueprint;
- restart preserves approval/activation;
- unresolved critical decisions block activation and surface through Atlas;
- target design never uses Actual refs as planned identity;
- every mandatory requirement/NFR has a verification contract.

---

## PIR-9 — Convergence correctness, evidence policy, and durable decisions

### Goal

Make Convergence multidimensional, revision-correct, durable, and safe for driving Atlas decisions.

### Required changes

1. Add typed comparator registry for all required dimensions.
2. Add evidence policy per Blueprint element.
3. Separate source/Twin/Blueprint/mapping/evidence revisions.
4. Persist mapping candidates, selected mappings, reports, element results, decisions, and completion reports.
5. Repair unavailable/materialized/observed mandatory-gap logic.
6. Repair completion policy: only CompletionEvaluator may produce final complete.
7. Add explicit Blueprint-element to PlanItem mapping.
8. Prove incremental/full equivalence for affected subsets.
9. Add rename/move/signature/schema matching and ambiguity handling.

### Acceptance

- source revision is never compared as a Twin revision;
- every mandatory element is unsatisfied until its evidence policy passes;
- interface/schema/behavior/state/resource divergences produce typed gaps;
- no `complete` decision occurs before all mandatory completion gates pass;
- decisions survive restart and are reproducible from immutable inputs.

---

## PIR-10 — Planner and authoritative PlanPool production integration

### Goal

Feed real Project Intelligence context into the actual planner and compile Blueprint gaps into authoritative PlanPool state.

### Required changes

1. Repair Coordinator planning path to return actual packages.
2. Integrate adapter into `app/api/atlas_pipeline.py` before `TaskPlanningRunner` advisory assembly.
3. Persist context manifest and input revision IDs on PlanPool metadata.
4. Repair Plan Compiler:
   - reject cycles/missing deps;
   - group coherent elements;
   - exclude pseudo-elements from file operations;
   - compute planning-envelope hash;
   - preserve real completed items and IDs;
   - map elements to PlanItems explicitly.
5. Translate compiled output through existing PlanPool authority, not direct private writes.
6. Shadow compare real planner inputs/outputs.
7. Block/refresh active planning on stale or unhealthy Twin state.

### Acceptance

- real Atlas plan creation invokes Project Intelligence in shadow and active modes;
- off mode remains unchanged;
- active PlanPool contains Blueprint/Twin/Convergence/manifest references;
- a dependency cycle is rejected before PlanPool creation;
- completed items remain unchanged during downstream replan;
- no private module store is accessed by Planner.

---

## PIR-11 — Proposal, Safe Apply, refresh, and generation-context integration

### Goal

Connect the real proposal and apply pipeline to manifest-backed generation context and post-apply Twin/Convergence updates.

### Required changes

1. Integrate generation adapter at the canonical Proposal input boundary.
2. Revalidate source and Twin revisions immediately before model invocation.
3. Materialize relevant current source ranges safely.
4. Persist manifest/base/Blueprint/Convergence refs in Proposal metadata.
5. Emit durable event after successful Safe Apply persistence.
6. Refresh Actual Twin using changed paths.
7. Run incremental Convergence and persist report/decision.
8. Preserve canonical Safe Apply success if projection/refresh fails; mark degraded and queue retry.
9. Add generation shadow comparison and regression telemetry.

### Acceptance

- real Proposal input contains Actual symbols/source, planned contracts, gaps, tests, preserve behavior, and uncertainty;
- stale generation blocks before model call;
- successful apply creates a new Twin revision and Convergence report;
- apply is never repeated on event replay;
- project/workspace isolation holds.

---

## PIR-12 — Verification, bounded recovery, checkpoint, and resume integration

### Goal

Close the existing-project loop from verification evidence to real Atlas continuation decisions.

### Required changes

1. Integrate verification adapter after canonical verification persistence.
2. Ingest real observations into Twin and reconcile.
3. Evaluate Convergence and Completion.
4. Persist a durable checkpoint with distinct source/apply/PlanPool revisions.
5. Map decisions to existing continuation, self-correction, replanning, Blueprint revision, critical-decision, and halt services.
6. Enforce bounded retry and preserve completed items.
7. Integrate resume with existing recovery/continuation API.
8. Detect external source changes and refresh/replan before continuing.
9. Coordinate apply/verification idempotency keys.

### Acceptance

- failed runtime evidence routes to local repair or downstream replan as appropriate;
- critical decision appears through the existing gate;
- unsafe decision halts without mutation;
- restart resumes from exact checkpoint without duplicate apply/verification;
- external change prevents blind resume;
- final completion uses canonical verification plus all Project Intelligence gates.

---

## PIR-13 — Real Greenfield state machine and end-to-end generation

### Goal

Generate, build, run, verify, repair, and resume real projects from the normal Atlas entrypoint.

### Required changes

1. Replace the helper-only Greenfield orchestrator with a durable state machine.
2. Accept typed canonical outcomes rather than Booleans.
3. Start from normal Atlas requirement/API entrypoint.
4. Create/approve Blueprint and authoritative PlanPool.
5. Generate coherent slices through Proposal.
6. Apply only through Safe Apply.
7. Refresh Twin and evaluate Convergence after every slice.
8. Use project-manifest-aware runtime command adapters.
9. Require readiness/health/browser/API evidence for start.
10. Perform real persistence restart check.
11. Inject one intermediate failure and prove repair/resume.
12. Retain all run artifacts.

### Required real scenarios

```text
single HTML with browser assertion
HTML + JS + CSS
Python CLI
FastAPI API
FastAPI + SQLite persistence/restart
frontend + backend application
```

Additional scenarios may be added, but comments and counts must be truthful.

### Acceptance

Every scenario creates a real temporary workspace and executes real allowlisted commands. Unavailable environments are recorded, not passed. At least the platform's supported scenarios must reach truthful completion.

---

## PIR-14 — Real consumer cutover, CI, platform, scale, and rollout evidence

### Goal

Prove operational readiness and migrate production consumers phase by phase.

### Required changes

1. Add CI workflows for focused, integration, restart, and fixture E2E suites.
2. Persist real consumer registry and phase call telemetry.
3. Execute cutover order with shadow parity.
4. Add import/dependency lint preventing new direct legacy consumers.
5. Execute rollback drills.
6. Run Windows, Linux, Docker, and Runpod evidence jobs where available.
7. Add large-repository and concurrency/load benchmarks.
8. Measure disk growth, compaction, export/import, and corruption recovery.
9. Implement durable telemetry thresholds and automatic phase rollback.
10. Keep unavailable platform evidence explicit.

### Acceptance

- CI results are attached to commits/PRs;
- at least planning, generation, verification, and recovery consumers use facades in production mode;
- each cutover has shadow evidence and rollback proof;
- regression budgets pass;
- platform and scale artifacts are stored and referenced in current status.

---

## PIR-15 — Real comparative benchmark, final active rollout, and legacy retirement

### Goal

Prove the final system under identical constraints, complete active rollout, and retire only proven-zero legacy paths.

### Required changes

1. Implement real benchmark runner from normal Atlas entrypoint.
2. Define and version task corpus and workspace seeds.
3. Execute both legacy and final arms repeatedly under identical constraints.
4. Compute metrics from actual artifacts, logs, token usage, outcomes, retries, and interventions.
5. Classify false success through independent acceptance checks.
6. Produce statistical summary and per-task failure taxonomy.
7. Promote all approved phases to active only if gates pass.
8. Verify consumer-zero and remove legacy paths in separate low-risk changes.
9. Test rollback before each removal.
10. Update all status/architecture/migration documents.

### Acceptance

- no benchmark metric is manually supplied as the result;
- real task corpus shows parity or superiority on verified outcomes without safety regression;
- active production path uses all four concrete facades;
- real Greenfield and existing-project loops pass;
- legacy consumer count is zero for each removed capability;
- cross-platform/live evidence gates are satisfied or program remains explicitly incomplete;
- master Definition of Done passes.

---

## Global testing order per package

```text
regression reproduction
-> focused component tests
-> contract/boundary tests
-> directly affected legacy tests
-> production integration tests
-> restart/fault tests
-> package acceptance scenario
-> milestone suite
```

## Global stop conditions

Stop only when proceeding requires:

- weakening safety/authority boundaries;
- destructive migration without approved backup/rollback;
- unsupported external infrastructure with no truthful unavailable path;
- a user decision on architecture/security/data loss that cannot be represented by existing critical-decision gates.

Do not stop because the package is large, tests are numerous, or live evidence requires multiple sequential changes. Record partial status truthfully and continue with the next coherent slice within the current package.
