# Atlas Project Intelligence Recovery — Master Goal

Status: canonical active corrective goal.

The PI-0..PI-25 sequence is retained as the **Foundation Track**. The active sequence is `PIR-0` through `PIR-15`, which converts the foundation into a durable, production-connected, operationally proven Project Intelligence system.

## 1. Mission

Complete the real Atlas loop:

```text
User Requirement
-> Requirement normalization / critical decisions
-> Actual Project Twin open or refresh
-> Architecture Blueprint create/revise/review/activate
-> Convergence evaluate
-> Plan Compiler -> authoritative PlanPool
-> Planner / Proposal generation
-> Safe Apply
-> Actual Twin refresh
-> Canonical Verification + runtime evidence ingest
-> Convergence reevaluate
-> continue | repair current | replan downstream | revise Blueprint |
   request critical decision | halt unsafe | complete
```

The system must work for both:

- existing projects, including repairs and scoped changes;
- empty or nearly empty projects, including real multi-file generation, build, start, test, runtime observation, restart, and completion evidence.

## 2. Non-negotiable truthfulness rule

A capability is complete only when all of the following are true:

1. its public contract exists;
2. a concrete implementation exists;
3. the real Atlas production path invokes it;
4. durable state survives process restart where required;
5. focused, integration, failure, and acceptance tests pass;
6. real-environment evidence exists for claims that require execution;
7. the current-status document records exact commands and evidence.

Mocks, injected success runners, manually authored metrics, class existence, or PR titles do not prove production completion.

## 3. Correct architecture

### 3.1 Public isolation units

```text
DigitalTwinModule
ArchitectureBlueprintModule
ConvergenceModule
ProjectIntelligenceModule
```

Each module may contain many internal services but exposes only its coarse facade and versioned DTOs.

### 3.2 Required concrete modules

The production composition root must construct:

```text
DigitalTwinModuleImpl
ArchitectureBlueprintModuleImpl
ConvergenceModuleImpl
ProjectIntelligenceCoordinator
```

Disabled implementations remain valid only for rollout `off` or explicit degraded fallback. Active mode must fail closed if a required concrete module is unavailable.

### 3.3 Authority boundaries

- Requirement system owns user intent and constraints.
- Blueprint owns approved target design.
- Workspace/Git owns source.
- Actual Twin owns revisioned interpretation of actual source and observed behavior.
- PlanPool owns execution state.
- Proposal owns generated patch artifacts.
- Safe Apply owns workspace mutation.
- Verification/runtime systems own observed outcomes.
- Convergence owns target-versus-actual reports and bounded decisions.
- Project Intelligence coordinates but does not bypass any authority.

## 4. Required Actual Twin capability

The final Twin must provide, through one concrete facade:

- project/workspace identity and safe source snapshots;
- durable source and Twin revision identities;
- full and incremental refresh;
- structural graph;
- whole-project semantic graph and linker;
- resolved and bounded-candidate call graph;
- per-callable control-flow graph;
- def-use and bounded interprocedural data flow;
- state, event, retry, timeout, rollback, and recovery transitions;
- concrete file, DB, API, network, process, dependency, config, UI, and rendering resources;
- durable canonical event/delivery projection;
- durable runtime observation ingestion;
- static/runtime reconciliation;
- source-range materialization;
- path, impact, test selection, and phase-specific context packages;
- explicit readiness, degradation, stale, and unavailable states.

Heuristic facts may remain, but must be labeled with derivation and confidence and may not be treated as verified.

## 5. Required Blueprint capability

The final Blueprint module must:

- create a structured target from Requirement + Actual context;
- support full-project, change-set, and repair scopes;
- represent exact files, components, interfaces, API/schema/data/config/dependency contracts, entrypoints, commands, runtime scenarios, NFRs, preserve behaviors, and verification contracts;
- persist immutable revisions, reviews, decisions, statuses, and active pointers;
- survive process restart;
- integrate clarification/critical-decision gates;
- never confuse planned refs with Actual refs.

## 6. Required Convergence capability

The final Convergence module must:

- map Blueprint elements to Actual facts with revisioned mapping history;
- compare structure, interface/signature, API/schema, data, config, dependency, behavior, state, side effect, delivery trace, runtime evidence, and NFR evidence;
- distinguish source revision from Twin revision;
- persist immutable reports and decisions;
- support bounded incremental reevaluation;
- never return complete unless the PI-15-style completion gate proves every mandatory requirement and mandatory Blueprint element has fresh required evidence;
- produce only bounded advisory actions, never perform execution directly.

## 7. Required Atlas production integration

The real Atlas application must invoke Project Intelligence at these boundaries:

```text
project/requirement start
planner context assembly
PlanPool construction
proposal input construction
pre-generation revision validation
post-Safe-Apply event/refresh
verification evidence normalization/ingest
post-verification Convergence
repair/replan/critical-decision routing
checkpoint/resume
final completion rollup
```

Integration must occur through adapters. Portable modules must not import FastAPI, UI, PlanPool storage, or private Atlas services.

## 8. Required Greenfield behavior

A normal Atlas request against an empty temporary workspace must:

1. detect Greenfield mode;
2. create and approve a valid Blueprint;
3. compile dependency-ordered PlanItems into the authoritative PlanPool;
4. generate coherent files through the Proposal path;
5. mutate only through Safe Apply;
6. refresh Actual Twin after each applied slice;
7. run real allowlisted build/test/start commands;
8. collect real runtime evidence;
9. repair or replan on an injected failure;
10. resume after process restart;
11. reach truthful completion only after all mandatory gates pass.

## 9. Rollout model

Rollout stages:

```text
off
-> shadow_inspection
-> shadow_planning
-> shadow_generation
-> active_planning
-> active_generation
-> active_verification
-> active_repair
-> supervised_greenfield
-> active
```

Each transition requires durable evidence, telemetry thresholds, rollback readiness, and no safety regression. Rollout state must survive restart.

## 10. Final comparative benchmark

The final benchmark must execute real tasks, not supplied metric dictionaries.

Both arms must use identical:

- model and sampling settings;
- repository revision and workspace seed;
- requirement;
- token/context budget;
- tools and authority;
- retry limit;
- time/resource budget.

Required task corpus:

- existing-project bug fixes;
- scoped feature additions;
- cross-file interface changes;
- runtime failures requiring repair;
- stale/external-change resume;
- single-file UI;
- multi-file web UI;
- Python CLI;
- FastAPI API;
- persistence application;
- frontend/backend application.

Required measured outcomes include verified autonomous completion, false success, recovery, regression escape, requirement coverage, impact/test-selection precision and recall, context usage, latency, intervention, resume fidelity, platform success, and cost per verified task.

## 11. Safety invariants

Never weaken or bypass:

- Requirement/clarification/critical-decision authority;
- PlanPool/workflow authority;
- profile, envelope, path, and base-revision checks;
- Safe Apply;
- command allowlists and sandbox rules;
- bounded retry and rollback;
- project/workspace isolation;
- direct push/merge/self-apply restrictions;
- truthful verification;
- `unavailable != passed`.

## 12. Final Definition of Done

The recovery program is COMPLETE only when:

1. all four production concrete facades are built and conformance-tested;
2. production Atlas constructs and uses them;
3. active Planner and Generator receive non-empty manifest-backed Actual/Blueprint/Convergence context;
4. Safe Apply and Verification automatically refresh/ingest/reevaluate;
5. the bounded Convergence decision changes real Atlas continuation behavior;
6. durable state survives restart and external-change detection works;
7. deep graph capabilities pass real-repository accuracy benchmarks;
8. real Greenfield scenarios generate, build, start, test, observe, repair, and resume;
9. Windows, Linux, Docker, and Runpod evidence is recorded, with unavailable kept explicit;
10. real comparative benchmark shows parity or superiority without safety regression;
11. legacy consumers reach zero in the approved cutover order;
12. rollback is tested before legacy removal;
13. all required CI and acceptance suites pass;
14. `docs/atlas_project_intelligence_recovery_current_status.md` records exact evidence;
15. no completion claim relies only on mocks, synthetic metrics, or document statements.
