# Atlas Project Intelligence — Detailed Implementation Plan

Status: canonical execution plan.

## 1. Execution model

The old PDT-0 through PDT-14 sequence is complete and is not restarted. This plan begins at `PI-0`.

Implement exactly one work package at a time unless the package explicitly defines inseparable sub-slices. A work package is complete only when its acceptance criteria and required tests pass and current status is updated.

General order:

```text
PI-0..PI-3   baseline, boundaries, contracts, module composition
PI-4..PI-9   Digital Twin production integration and deep graph intelligence
PI-10..PI-12 Blueprint Module
PI-13..PI-15 Convergence Module
PI-16..PI-19 Planner, Generator, Verification, and Resume integration
PI-20..PI-22 Greenfield generation
PI-23..PI-25 reorganization, rollout, and final benchmark
```

## 2. Global implementation rules

For every package:

1. inspect current main and current status;
2. inventory target symbols, direct dependencies, direct callers, and tests;
3. reuse existing behavior through adapters before replacing it;
4. add or update contracts before consumers;
5. implement the smallest coherent vertical slice;
6. run focused tests, syntax/type checks, affected tests, and package acceptance scenarios;
7. record executed evidence and unavailable checks truthfully;
8. update `docs/atlas_project_intelligence_current_status.md`;
9. proceed automatically when all acceptance criteria pass;
10. do not push, merge, or weaken safety boundaries unless explicitly instructed.

No package may introduce a second competing Digital Twin, context system, memory system, or execution authority.

---

# Milestone A — Baseline and module boundaries

## PI-0 — Production baseline and consumer map

### Goal

Create an executable baseline of current project-analysis, context, impact, verification, and Project Twin behavior before production reorganization.

### Required outputs

- `docs/atlas_project_intelligence_existing_capability_map.md`
- `docs/atlas_project_intelligence_consumer_map.md`
- `docs/atlas_project_intelligence_migration_matrix.md`
- `tests/test_project_intelligence_baseline.py`

### Inventory scope

At minimum inspect:

- `agent/project_twin/`
- `agent/atlas_repo_index_*`
- `agent/atlas_code_intel_*`
- `agent/atlas_code_explorer.py`
- `agent/atlas_project_inspection_service.py`
- `agent/atlas_git_inspection_service.py`
- `agent/atlas_test_impl_linker.py`
- `agent/context_builder.py`
- `agent/atlas_repo_context_*`
- `agent/atlas_context_refresh_*`
- `agent/atlas_planner_packaging_*`
- `agent/atlas_plan_item_impact_map_service.py`
- `agent/atlas_verification_*`
- Planner, Proposal, Safe Apply, runtime, and final-rollup call sites.

### Migration classification

Every relevant owner receives one classification:

- KEEP — remains canonical;
- ADAPT — retained behind a new facade;
- REPLACE — replaced after parity;
- REMOVE — deleted only after consumer migration and rollback evidence.

### Acceptance criteria

- all direct consumers are recorded by symbol;
- current duplication is explicitly identified;
- authoritative owners are identified;
- baseline tests pin current public behavior;
- no production behavior is changed;
- the old PDT status is recorded as Core v1 complete, not full program complete.

### Required tests

```text
pytest -q tests/test_project_intelligence_baseline.py
pytest -q tests/test_project_twin_baseline.py
python -m py_compile <new baseline test helpers>
```

## PI-1 — Module facade contracts and boundary tests

### Goal

Implement versioned contracts and coarse-grained facades for the four modules.

### Primary files

```text
agent/project_intelligence/contracts.py
agent/project_intelligence/facade.py
agent/project_twin/facade.py
agent/architecture_blueprint/contracts.py
agent/architecture_blueprint/facade.py
agent/project_convergence/contracts.py
agent/project_convergence/facade.py
tests/test_project_intelligence_contracts.py
tests/test_project_intelligence_boundaries.py
```

### Requirements

- contracts depend only on stdlib, typing, and schema library already used by the project;
- public models serialize deterministically;
- compatibility readers accept `atlas.project_twin.v1` where applicable;
- no facade exposes a private store object;
- architecture tests reject forbidden imports;
- no implementation is required beyond safe unavailable/disabled stubs.

### Acceptance criteria

- four facades are importable;
- old Project Twin contracts remain readable;
- forbidden dependency tests pass;
- disabled facades preserve current Atlas behavior.

## PI-2 — Persistence and migration foundation

### Goal

Add isolated, revisioned persistence for Blueprint, Convergence, Project Intelligence jobs, and context manifests without rewriting canonical Atlas stores.

### Primary files

```text
agent/architecture_blueprint/store.py
agent/architecture_blueprint/migrations.py
agent/project_convergence/store.py
agent/project_convergence/migrations.py
agent/project_intelligence/store.py
agent/project_intelligence/migrations.py
```

### Requirements

- SQLite adapters remain replaceable behind module facades;
- project/workspace isolation;
- immutable Blueprint revision rows;
- atomic transactions and rollback;
- idempotency and stale-revision rejection;
- point-in-time reads;
- integrity check and explicit corruption state;
- no migration of PlanPool, Conversation, Nexus, or Memory canonical data.

### Acceptance criteria

- transaction failure leaves no partial revision;
- duplicate idempotency key is harmless;
- stale parent revision is rejected;
- project isolation tests pass;
- migrations are repeatable and rollback-safe.

## PI-3 — Project Intelligence composition root and rollout model

### Goal

Create the composition root that wires the modules through facades and supports off/shadow/active phase rollout.

### Primary files

```text
agent/project_intelligence/factory.py
agent/project_intelligence/coordinator.py
agent/project_intelligence/rollout.py
agent/project_intelligence/telemetry.py
```

### Requirements

- module dependencies are injected;
- feature-off path has no required new persistence;
- shadow computes but does not alter Planner/Generator inputs;
- rollout supports planning, generation, verification, repair, and greenfield phases;
- old Project Twin environment variables map to compatibility configuration;
- rollback to legacy path is immediate.

### Acceptance criteria

- off mode is behaviorally equivalent to baseline;
- shadow mode produces comparison artifacts only;
- no direct private-store calls from coordinator consumers;
- configuration parsing is deterministic and tested.

---

# Milestone B — Digital Twin Module production integration

## PI-4 — Project identity, mode detection, and lifecycle

### Goal

Make Project Twin construction and readiness part of real project lifecycle.

### Primary files

```text
agent/project_twin/lifecycle.py
agent/project_twin/project_identity.py
agent/project_intelligence/project_mode.py
agent/project_twin/jobs.py
```

### Requirements

- stable logical project ID;
- separate workspace/worktree ID;
- empty, greenfield_partial, existing, generated_unverified, imported_unknown modes;
- startup recovery for interrupted projection jobs;
- readiness states absent/building/ready/stale/degraded/corrupt/disabled;
- parser-version and source-revision stale detection;
- initial full build and incremental refresh.

### Acceptance criteria

- empty directory creates a valid repository-level Twin;
- worktrees do not leak data;
- external changes mark stale or trigger refresh;
- corrupt DB fails closed and supports rebuild;
- restart resumes or safely retries jobs.

## PI-5 — Canonical event bridge and delivery trace expansion

### Goal

Connect real Atlas canonical events to Twin projection using journal/outbox semantics.

### Primary files

```text
agent/project_twin/event_bridge.py
agent/project_twin/events.py
agent/project_twin/intent_trace.py
selected Atlas journal/storage producer adapters
```

### Event scope

Implement the required event catalog in the contracts document.

### Requirements

- canonical operation commits before projection;
- projection is at-least-once and idempotent;
- projection failure marks degraded and queues retry;
- correlation/run/pool/item IDs preserved;
- no dual-write rollback of successful Safe Apply;
- failure and revision history remain queryable.

### Acceptance criteria

- a real requirement/plan/proposal/apply/verification flow produces delivery trace;
- duplicate replay does not duplicate facts;
- missing links create diagnostics, not fabricated edges;
- canonical stores remain unchanged by projection.

## PI-6 — Static and semantic graph v2

### Goal

Replace compatibility-level name extraction with a real semantic foundation while preserving old adapters until parity.

### Internal capabilities

- repository/file/package/module/symbol/type graph;
- import and module resolution;
- definition/reference;
- alias and re-export;
- inheritance, override, Protocol/interface implementation;
- decorator and dependency-injection relationships;
- resolved and candidate call targets;
- Python first, then JS/TS/Vue basic semantic support.

### Primary files

```text
agent/project_twin/analyzers/registry.py
agent/project_twin/analyzers/python.py
agent/project_twin/analyzers/javascript.py
agent/project_twin/analyzers/typescript_vue.py
agent/project_twin/lsp_adapter.py
agent/project_twin/graph/semantic.py
```

### Requirements

- analyzer adapter exposes one coarse `analyze` operation;
- capability and version manifest;
- deterministic canonical refs;
- unresolved dynamic calls represented as candidates with confidence;
- LSP unavailable falls back to AST and records degradation;
- incremental invalidation tracks changed definitions and references.

### Acceptance criteria

- exact same-name functions in different modules are not collapsed;
- aliases and imports resolve correctly in fixtures;
- call targets distinguish resolved and may-call;
- JS/TS/Vue imports and component basics are represented;
- old CodeIntel parity metrics are recorded.

## PI-7 — Behavioral graph v2

### Goal

Implement the previously missing behavioral intelligence.

### Internal capabilities

- control-flow basic blocks;
- branch, loop, return, exception, finally, async boundaries;
- intraprocedural data flow;
- interprocedural parameter/return propagation for supported cases;
- state mutation and transitions;
- event producer/consumer/handler relations;
- retry, timeout, rollback, and recovery paths;
- concrete side-effect resources;
- API -> handler -> service -> repository -> query -> table;
- UI control -> event -> state -> API -> response -> render.

### Requirements

- every inferred fact has derivation, confidence, and provenance;
- unsupported constructs produce diagnostics;
- heuristics never become verified without evidence;
- incremental rebuild invalidates dependent behavioral facts;
- static graph identities are reused rather than duplicated.

### Acceptance criteria

- fixture paths cover branch/error/retry behavior;
- HTTP request-to-persistence path is queryable;
- UI event-to-render path is queryable for supported fixtures;
- concrete file/table/route targets are recorded where resolvable;
- false certainty tests pass.

## PI-8 — Runtime intelligence and reconciliation v2

### Goal

Connect real verification and runtime outputs to Runtime Graph.

### Inputs

- pytest results and coverage;
- Playwright trace, browser network, console;
- API verification;
- Atlas Play session observations;
- supported DB/file/process observations;
- latency and memory evidence where available.

### Requirements

- normalize passed/failed/observed/unavailable;
- map stack frames and coverage to actual symbols;
- preserve source revision;
- confirm, partially confirm, contradict, not-observe, or mark unavailable;
- stale observations do not verify new source revisions;
- collectors never gain execution authority.

### Acceptance criteria

- real verification result is ingested automatically;
- unavailable remains unavailable throughout UI and rollup;
- contradicted static fact is retained historically;
- verified path requires matching revision evidence;
- collector failure cannot mark task success.

## PI-9 — Context, path, impact, and test selection v2

### Goal

Make the Digital Twin useful to production consumers through stable query/context packages.

### Requirements

- graph-neighborhood candidate generation;
- impact and path integration;
- objective and phase relevance;
- freshness and contradiction penalties;
- source excerpts materialized from current workspace;
- requirements, interfaces, paths, state/events, side effects, tests, runtime, incidents, memory, skills, Nexus, preserve behavior, and uncertainty sections;
- context manifest persisted;
- bounded traversal and token budget;
- impact precision/recall and test recommendation metrics.

### Acceptance criteria

- no full graph dump into prompts;
- target and mandatory requirements receive priority;
- stale/contradicted information is labeled or excluded;
- source excerpts match the manifest source revision;
- context can be generated without Atlas-specific schemas.

---

# Milestone C — Architecture Blueprint Module

## PI-10 — Blueprint model, store, and lifecycle

### Goal

Implement immutable Blueprint revisions and lifecycle behind one facade.

### Requirements

- full_project, change_set, repair scopes;
- proposed/reviewed/approved/active/materializing/satisfied/diverged/superseded/rejected states;
- one active revision per applicable scope policy;
- parent revision and diff;
- architecture decisions and authority;
- no planned element represented as an Actual reference.

### Acceptance criteria

- activated revisions are immutable;
- revision creates a child;
- user decision cannot be fabricated by LLM output;
- project isolation and point-in-time reads pass.

## PI-11 — Blueprint generation, review, and validation

### Goal

Generate complete target contracts for existing and greenfield projects.

### Validation dimensions

- requirement coverage;
- exact file manifest;
- components and dependency order;
- interfaces and schemas;
- API/data/persistence contracts;
- behavior/error/recovery contracts;
- entrypoint, build, startup, and test commands;
- runtime scenarios and nonfunctional requirements;
- dependency cycles and unsafe designs;
- unresolved critical decisions.

### Acceptance criteria

- vague structural plans are rejected;
- empty-project Blueprint includes exact materialization targets;
- existing small change produces Change Blueprint rather than full redesign;
- validation is deterministic where possible;
- review diagnostics are machine-readable.

## PI-12 — Blueprint-to-Actual mapping hints

### Goal

Provide explicit expected actual references and deterministic mapping hints without coupling Blueprint to Twin internals.

### Relations

```text
materialized_as
implemented_by
realized_by
satisfies
verified_by
diverges_from
blocked_by
```

### Acceptance criteria

- mapping uses public snapshots/packages;
- Blueprint remains valid when Twin store implementation changes;
- heuristically suggested mapping is never silently accepted as verified;
- mapping history follows Blueprint and Twin revisions.

---

# Milestone D — Convergence Module

## PI-13 — Deterministic matcher and multidimensional evaluator

### Goal

Evaluate Blueprint elements against one immutable Actual Twin revision.

### Dimensions

- structural;
- interface;
- behavioral;
- data/persistence;
- dependency/configuration;
- verification/runtime;
- nonfunctional;
- delivery trace.

### Acceptance criteria

- absent, partial, materialized, observed, verified, divergent, blocked, stale are distinct;
- file existence does not imply behavior verification;
- stale evidence cannot satisfy mandatory verification;
- mismatches include explanation and evidence refs;
- matching is reproducible.

## PI-14 — Convergence decision policy and incremental reevaluation

### Goal

Convert evaluated gaps into bounded next actions without executing them.

### Decisions

```text
continue
complete
repair_current_item
replan_downstream
revise_blueprint
request_critical_decision
halt_unsafe
```

### Requirements

- deterministic rules precede optional LLM advice;
- changed refs limit incremental reevaluation;
- local mismatch does not trigger whole-project redesign;
- interface changes may replan only affected downstream items;
- unsafe requirement never becomes automatic execution.

### Acceptance criteria

- decision matrix tests cover all actions;
- incremental and full reports agree for affected elements;
- mandatory gap prevents complete;
- policy does not mutate Blueprint, PlanPool, or workspace.

## PI-15 — Final completion and requirement-evidence integration

### Goal

Integrate Convergence into final rollup without replacing canonical verification authority.

### Required completion gates

- mandatory requirement coverage 100%;
- zero mandatory Blueprint gaps;
- zero unresolved critical decisions;
- zero failed required verification;
- zero stale mandatory evidence;
- no unsafe halt condition.

### Acceptance criteria

- false-success scenarios fail rollup;
- unavailable evidence remains incomplete;
- delivery path is queryable for every mandatory requirement;
- legacy rollup remains fallback in off mode.

---

# Milestone E — Atlas planning, generation, verification, and recovery integration

## PI-16 — Planning envelope and Blueprint Plan Compiler

### Goal

Turn Actual/Blueprint/Convergence state into PlanPool through a stable planning package.

### Requirements

- Architecture Planning, Delivery Planning, and Repair Planning are explicit phases;
- Blueprint dependency graph provides deterministic order;
- LLM proposes semantic grouping and implementation strategy, not identity bookkeeping;
- completed items are not recreated;
- PlanPool stores revision and manifest references;
- old PlanPools load with defaults.

### Acceptance criteria

- empty project produces create-file/create-structure items;
- existing project produces scoped modify items;
- downstream-only replan preserves completed items;
- requirement and Blueprint element mappings are complete.

## PI-17 — Planner production integration

### Goal

Integrate `ProjectIntelligenceModule.prepare_planning_context` into actual Planner path.

### Target integration

- `AtlasPlannerBridge` and planning runner input;
- PlanPool metadata and artifacts;
- shadow comparison telemetry.

### Acceptance criteria

- off mode uses legacy context only;
- shadow mode does not change planner input;
- active mode includes manifest-backed context;
- stale/degraded readiness is explicit;
- planner does not access module stores directly.

## PI-18 — Generator and repair production integration

### Goal

Integrate generation context into `AtlasPatchProposalService` and repair flows.

### Required context

- current target content and base revision;
- Blueprint contracts;
- actual symbols/interfaces;
- behavior paths and side effects;
- convergence gaps;
- preserve behavior;
- required evidence and prohibited divergence.

### Acceptance criteria

- stale Actual revision blocks or refreshes before generation;
- missing imaginary symbols are not presented as real;
- multi-file names and contracts remain coherent;
- Proposal stores context manifest;
- repair uses actual failure evidence and bounded decisions.

## PI-19 — Verification, checkpoint, and resume integration

### Goal

Close the loop and make long-running development restart-safe.

### Checkpoint state

```text
requirement revision
Blueprint revision
Actual Twin revision
Convergence report
PlanPool revision
current item
last successful evidence
rollout mode
```

### Acceptance criteria

- verification automatically ingests runtime observations;
- post-verification Convergence runs;
- restart resumes from exact revisions;
- external source changes are detected before continuation;
- no duplicate apply or verification on replay;
- rollback remains available.

---

# Milestone F — Greenfield generation

## PI-20 — Greenfield bootstrap orchestrator

### Goal

Create a dedicated orchestration mode that still uses normal PlanPool, Proposal, Safe Apply, Verification, and Project Intelligence boundaries.

### Requirements

- Project mode detection selects Greenfield path;
- active Blueprint required before broad generation;
- exact file manifest, entrypoint, build/start/test contracts required;
- dependency order compiled into PlanItems;
- generation occurs one coherent slice at a time;
- Actual Twin refresh and Convergence after each apply.

### Acceptance criteria

- empty directory is supported;
- no broad file generation without reviewed Blueprint;
- interruption resumes safely;
- the orchestrator cannot bypass Safe Apply.

## PI-21 — Coherent multi-file generation and consistency validation

### Required checks

- imports resolve;
- assets referenced by HTML/Vue exist;
- frontend and backend APIs agree;
- request/response schemas agree;
- dependencies exist in manifests;
- entrypoints and commands exist;
- tests use actual interfaces;
- generated paths belong to Blueprint manifest;
- unexpected files are classified.

### Acceptance criteria

- mismatches become typed Convergence gaps;
- local repair is attempted before Blueprint revision;
- missing dependency and missing file have separate recovery policies;
- no generated placeholder counts as completion.

## PI-22 — Greenfield build/run/test and real E2E

### Runtime adapter contract

A coarse `ProjectRuntimeAdapter` detects runtime profile and provides safe build, test, and startup commands under existing command authority.

### Required E2E scenarios

1. single HTML;
2. HTML/JS/CSS application;
3. Python CLI;
4. FastAPI API;
5. FastAPI plus persistence;
6. Vue plus FastAPI;
7. restart during generation;
8. intermediate item failure and recovery.

### Acceptance criteria

- tests start from normal Atlas API/entrypoint, not synthetic Twin injection;
- build/start/runtime evidence is captured;
- persistence is verified across restart when required;
- unsupported environment is unavailable, not passed.

---

# Milestone G — Reorganization, rollout, and completion

## PI-23 — Existing capability consolidation and consumer cutover

### Goal

Migrate duplicated consumers to module facades in safe order.

### Cutover order

```text
inspection/read-only API
-> planning context
-> generation context
-> impact map
-> verification recommendation
-> repair
-> final rollup
```

### Requirements

- compatibility adapters first;
- legacy/new shadow comparison;
- consumer count tracked;
- no deletion before parity;
- canonical authorities remain.

### Acceptance criteria

- new consumers use facade only;
- parity exceptions are documented;
- rollback is tested;
- forbidden direct dependencies are zero for migrated consumers.

## PI-24 — Cross-platform, scale, storage, and rollout hardening

### Requirements

- Windows, Linux, Docker, Runpod scenarios;
- large-repository benchmark;
- bounded traversal and context latency;
- revision retention and compaction;
- integrity check, export/import, rebuild;
- job coalescing and restart recovery;
- phase rollout gates and telemetry.

### Acceptance criteria

- baseline regression budget is defined and enforced;
- no project data leakage;
- no unbounded prompt growth;
- phase rollback works;
- unavailable platform evidence is explicit.

## PI-25 — Final comparative benchmark and legacy retirement

### Goal

Demonstrate improvement and retire only proven redundant paths.

### Benchmark constraints

Use the same model, repository, requirement, token budget, tool authority, and retry limit.

### Metrics

- verified autonomous completion;
- false success;
- autonomous recovery;
- regression escape;
- requirement coverage;
- mandatory Blueprint convergence;
- impact precision/recall;
- test recommendation precision;
- context tokens and latency;
- human intervention;
- resume fidelity;
- cross-platform success;
- cost per verified task.

### Retirement conditions

A legacy path may be removed only when:

- direct consumer count is zero;
- shadow parity or documented superiority is established;
- affected tests and real E2E pass;
- rollback or recovery exists;
- data migration is unnecessary or verified;
- docs and status are updated.

### Final acceptance

All final Definition of Done items in the master goal and test plan pass. Current status is set to COMPLETE only then.

---

## 3. Work-package status rules

Allowed status values:

```text
Not Started
In Progress
Blocked
Completed
Superseded
```

A package may not be marked Completed from code review alone. The status entry must include:

- commit or PR reference;
- changed modules;
- exact executed test commands and results;
- unavailable checks;
- migration or rollout state;
- remaining known limitations;
- next package.

## 4. Stop conditions

Stop only for:

- destructive or safety-sensitive user decision;
- schema migration with credible data-loss risk;
- architecture contradiction that cannot be locally adapted safely;
- required environment unavailable with no trustworthy alternative;
- requirement to weaken approval, Safe Apply, rollback, allowed paths, command authority, retry bounds, project isolation, or truthful verification.

Implementation size, context size, and test duration are not blockers.
