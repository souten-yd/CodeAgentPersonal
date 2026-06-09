# Atlas Project Intelligence — Agent Instructions

This repository has an active multi-package implementation goal for Atlas Project Intelligence.

The previous Project Digital Twin packages `PDT-0` through `PDT-14` are complete as **Project Digital Twin Core v1**. Do not restart them. The active sequence begins at the work package selected by `docs/atlas_project_intelligence_current_status.md`, initially `PI-0`.

## Canonical documents

Read in this order:

1. `AGENTS.md`
2. `docs/atlas_project_intelligence_master_goal.md`
3. `docs/atlas_project_intelligence_current_status.md`
4. the current work package in `docs/atlas_project_intelligence_implementation_plan.md`
5. relevant sections of `docs/atlas_project_intelligence_architecture.md`
6. relevant sections of `docs/atlas_project_intelligence_detailed_design.md`
7. relevant sections of `docs/atlas_project_intelligence_contracts.md`
8. relevant sections of `docs/atlas_project_intelligence_test_plan.md`
9. `docs/atlas_project_intelligence_migration_plan.md` when touching existing capabilities or consumers
10. `docs/atlas_project_intelligence_agent_entrypoint.md`
11. target code, direct dependencies, direct callers, and related tests

The old `docs/atlas_project_digital_twin_*` documents are historical/reference documents for Core v1. They are not the active overall goal.

## Goal-mode instruction

```text
Read AGENTS.md and execute the active Atlas Project Intelligence goal through completion.
Start from the current work package in docs/atlas_project_intelligence_current_status.md.
Implement work packages sequentially, run the required tests, update current status after each package, and continue automatically while acceptance criteria pass.
Do not restart PDT-0 through PDT-14. Do not stop at planning. Do not push, merge, self-apply, weaken safety boundaries, or delete legacy paths before migration gates pass.
```

## Execution loop

For each work package:

1. verify current status against current code;
2. inspect the package requirements and relevant design sections;
3. inspect target symbols, direct callers, dependencies, and related tests;
4. reuse existing behavior through adapters where appropriate;
5. implement contracts before active consumers;
6. make the smallest coherent vertical change;
7. preserve off/shadow/rollback behavior;
8. run focused tests, syntax/type/import checks, affected tests, and the package acceptance scenario;
9. fix failures caused by the change;
10. update `docs/atlas_project_intelligence_current_status.md` with exact evidence;
11. continue automatically to the next package when acceptance criteria pass.

Do not perform a repository-wide reread after PI-0 unless targeted symbol discovery fails.

## Module boundary rule

Isolation is at module level, not at every helper function.

Required public facades:

```text
DigitalTwinModule
ArchitectureBlueprintModule
ConvergenceModule
ProjectIntelligenceModule
```

Internal analyzers, stores, matchers, policies, and helpers remain private implementation details.

Forbidden dependencies include:

```text
Planner -> Digital Twin private store
Generator -> Blueprint private store
Convergence -> SQLite private tables
Digital Twin core -> PlanPool storage
Blueprint core -> Digital Twin private objects
portable modules -> FastAPI, UI, or web/js
```

Use module facades or Atlas integration adapters.

## Existing feature reorganization

When changing existing analysis, context, impact, trace, or verification-support code:

- classify the capability as KEEP, ADAPT, REPLACE, or REMOVE;
- introduce compatibility/facade behavior before cutover;
- use shadow comparison where required;
- migrate consumers in the canonical order;
- do not create permanent duplicate systems;
- do not delete legacy paths until all retirement gates in the migration plan pass.

## Authority rules

- Requirement system owns user intent and constraints.
- Architecture Blueprint owns approved target design.
- Workspace/Git owns actual source.
- Digital Twin owns revisioned interpretation of actual structure and behavior.
- PlanPool/workflow owns execution state.
- Safe Apply owns workspace mutation.
- Verification/runtime systems own observed outcomes.
- Convergence owns target-versus-actual gap reports, not execution.
- Nexus owns external evidence.
- Memory owns durable knowledge.

No projection or inference may overwrite its canonical owner.

## Safety invariants

Never weaken or bypass:

- PlanPool/workflow authority;
- clarification and critical-decision gates;
- profile, envelope, and allowed-path checks;
- Safe Apply and base-revision preconditions;
- rollback and bounded retry;
- command allowlists;
- direct merge, remote push, and self-apply restrictions;
- project/workspace isolation;
- truthful verification;
- the rule that unavailable is not passed.

Project Intelligence is not execution authority.

## Testing and evidence

Required order:

```text
focused tests
-> syntax/type/import checks
-> directly affected tests
-> package acceptance scenario
-> milestone integration tests when applicable
```

Do not claim a test passed unless it was executed. Record exact commands and results in current status. Record unavailable tools or environments explicitly and never convert them to success.

## Stop conditions

Stop only when:

- destructive or safety-sensitive user judgment is required;
- a migration has credible data-loss risk without approved backup/rollback;
- current code contradicts the canonical architecture too broadly for safe local adaptation;
- a required environment is unavailable with no trustworthy alternative verification;
- proceeding requires weakening approval, Safe Apply, rollback, retry, command authority, isolation, or truthful verification.

Implementation size, context size, test duration, and remaining package count are not blockers.

## Completion

Do not mark the overall goal complete before `PI-25` and all master-goal Definition of Done conditions pass. Production integration, deep graph implementation, Blueprint, Convergence, Greenfield E2E, reorganization, rollout, cross-platform evidence, and the final comparative benchmark are mandatory.
