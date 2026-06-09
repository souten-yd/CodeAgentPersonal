# Atlas Project Intelligence — Codex Goal Entrypoint

This is the canonical execution entrypoint for Codex goal mode.

## 1. Read order

Read in this order:

1. `AGENTS.md`
2. `docs/atlas_project_intelligence_master_goal.md`
3. `docs/atlas_project_intelligence_current_status.md`
4. the current work package in `docs/atlas_project_intelligence_implementation_plan.md`
5. relevant sections of `docs/atlas_project_intelligence_architecture.md`
6. relevant sections of `docs/atlas_project_intelligence_contracts.md`
7. relevant sections of `docs/atlas_project_intelligence_test_plan.md`
8. `docs/atlas_project_intelligence_migration_plan.md` when touching existing capabilities or consumers
9. target files, direct dependencies, direct callers, and related tests

The old `atlas_project_digital_twin_*` documents describe completed Core v1 and remain historical/reference material. Do not restart PDT-0 through PDT-14.

## 2. Goal-mode command

Use the following goal:

```text
Read AGENTS.md and execute the active Atlas Project Intelligence goal through completion.
Start from the current work package in docs/atlas_project_intelligence_current_status.md.
Implement work packages sequentially, run the required tests, update current status after each package, and continue automatically while acceptance criteria pass.
Do not restart PDT-0 through PDT-14. Do not stop at planning. Do not push, merge, self-apply, weaken safety boundaries, or delete legacy paths before migration gates pass.
```

## 3. Execution loop

For each work package:

1. verify that current status and current main agree;
2. read only the current package and relevant design sections;
3. inspect target symbols, direct callers, dependencies, and related tests;
4. identify reusable current code and its KEEP/ADAPT/REPLACE/REMOVE status;
5. implement public contracts before active consumers;
6. implement the smallest coherent vertical slice;
7. preserve off/shadow/rollback behavior where required;
8. run focused tests;
9. run syntax/type/import checks;
10. run affected tests;
11. run the package acceptance scenario;
12. fix failures caused by the change;
13. update current status with exact evidence;
14. continue to the next package automatically when all criteria pass.

Do not reread the whole repository for every package. Broad inventory is required in PI-0; later packages use current status and targeted investigation.

## 4. Module-boundary discipline

The public isolation units are modules, not every helper function.

Required public facades:

```text
DigitalTwinModule
ArchitectureBlueprintModule
ConvergenceModule
ProjectIntelligenceModule
```

Internal analyzers, repositories, matchers, policies, and helpers remain private implementation details unless the canonical contracts explicitly expose them.

Forbidden dependency examples:

```text
Planner -> Digital Twin private store
Generator -> Blueprint private store
Convergence -> SQLite private tables
Digital Twin core -> PlanPool storage
Blueprint core -> Digital Twin private objects
portable modules -> FastAPI, UI, web/js
```

Use a module facade or Atlas integration adapter instead.

## 5. Existing capability reorganization

When modifying existing analysis, context, impact, or verification code:

1. consult the migration plan;
2. classify the capability or consumer as KEEP, ADAPT, REPLACE, or REMOVE;
3. introduce facade/compatibility behavior before cutover;
4. run shadow comparison where specified;
5. migrate consumers in the planned order;
6. do not delete old behavior in the same change as a high-risk cutover;
7. remove only after all retirement gates pass.

Do not create permanent duplicate Project Intelligence paths.

## 6. Source-of-truth rules

- Requirement system owns user intent and constraints.
- Architecture Blueprint owns approved target design.
- Workspace/Git owns actual source.
- Digital Twin owns the revisioned interpretation of actual structure and behavior.
- PlanPool owns execution state.
- Safe Apply owns workspace mutation.
- Verification/runtime systems own observed outcomes.
- Convergence owns target-versus-actual gap reports, not execution.
- Nexus owns external research.
- Memory owns durable knowledge.

A projection or inference must not overwrite its canonical owner.

## 7. Safety invariants

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

Project Intelligence is advisory/contextual except for its own immutable artifacts and deterministic gap decisions. It is not mutation authority.

## 8. Testing rules

Required order:

```text
focused tests
-> syntax/type/import checks
-> directly affected tests
-> package acceptance scenario
-> milestone integration tests when a milestone closes
```

Do not claim a test passed unless executed. Record exact commands and results in current status.

When an environment or tool is unavailable:

- record `unavailable` and reason;
- record what remains unverified;
- use a trustworthy alternative only when the test plan allows it;
- never reinterpret unavailable as success.

## 9. Status update rules

After every package update `docs/atlas_project_intelligence_current_status.md` with:

```text
Work package
Status
Commit/PR
Changed modules/files
Executed commands and exact results
Unavailable checks
Safety invariants checked
Migration/rollout state
Known limitations
Next package
Blocker, if any
```

Only the current-status document selects the next package. Planning documents do not prove completion.

## 10. Stop conditions

Stop and record a blocker only when:

- destructive or safety-sensitive user judgment is required;
- a migration has credible data-loss risk without an approved backup/rollback decision;
- current main contradicts the canonical architecture so broadly that local adaptation is unsafe;
- a required environment is unavailable and no trustworthy verification alternative exists;
- proceeding requires weakening approval, Safe Apply, rollback, retry, command authority, project isolation, or truthful verification.

Implementation size, context size, test duration, and the number of remaining packages are not blockers.

## 11. Completion rule

Do not mark the program complete before PI-25 and the master-goal Definition of Done pass.

A module can be locally complete while the program remains active. Production integration, real E2E, reorganization, rollout, cross-platform evidence, and the final comparative benchmark are mandatory.
