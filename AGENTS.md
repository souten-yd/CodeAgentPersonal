# Atlas Project Intelligence Recovery — Agent Instructions

The active implementation track is `PIR-0..PIR-15`.

`PDT-0..PDT-14` remain Project Digital Twin Core v1 history. `PI-0..PI-25` remain the Foundation Track: useful contracts, helpers, and tests, but not proof that the production loop is complete. Do not restart or delete them.

## Read order

1. `AGENTS.md`
2. `docs/atlas_project_intelligence_recovery_master_goal.md`
3. `docs/atlas_project_intelligence_pi0_25_implementation_audit.md`
4. `docs/atlas_project_intelligence_recovery_current_status.md`
5. current package in `docs/atlas_project_intelligence_recovery_implementation_plan.md`
6. relevant sections of `docs/atlas_project_intelligence_recovery_detailed_design.md`
7. relevant sections of `docs/atlas_project_intelligence_recovery_test_plan.md`
8. existing Project Intelligence decisions, contracts, architecture, and migration documents
9. target code, public contracts, direct callers, dependencies, and tests

## Goal instruction

```text
Read AGENTS.md and execute the active Atlas Project Intelligence Recovery goal through completion.
Start from the package selected by docs/atlas_project_intelligence_recovery_current_status.md, initially PIR-0.
Treat PI-0 through PI-25 as the Foundation Track, not as proof of production completion.
Implement PIR packages sequentially, test at the required proof level, update recovery current status after every coherent slice, and continue automatically while acceptance criteria pass.
Do not stop at planning. Do not claim production integration from adapter-only tests, live E2E from injected success runners, or benchmark improvement from manually supplied metrics.
Do not weaken safety boundaries or remove legacy paths before migration gates pass.
```

## Proof levels

Use only:

```text
not_started
in_progress
component_complete
production_connected
acceptance_complete
blocked
```

Focused tests can prove `component_complete`. A real Atlas caller is required for `production_connected`. Real workspace, command, restart, platform, or benchmark evidence is required when the package acceptance criteria demand it.

## Execution loop

For the current package:

1. verify current status against current code;
2. reproduce the audited defect or missing production path;
3. inspect public contracts and real callers;
4. implement the smallest coherent vertical slice;
5. preserve off, shadow, active, and rollback behavior;
6. run regression, focused, conformance, and affected tests;
7. run required production integration, restart, fault, and acceptance tests;
8. record exact evidence and unavailable checks;
9. update recovery current status with the correct proof level;
10. continue until package acceptance passes, then advance.

## Required dependency order

```text
baseline and regression locks
-> durable concrete modules
-> production composition
-> Twin lifecycle/event/runtime/query loop
-> semantic/CFG/data-flow/state/resource graphs
-> durable Blueprint and Convergence
-> Planner and PlanPool integration
-> Proposal, Safe Apply, and refresh integration
-> Verification, recovery, checkpoint, and resume
-> real Greenfield E2E
-> CI, platform, scale, and consumer cutover
-> real benchmark and legacy retirement
```

Do not start broad deep-graph rewrites before concrete durable facades and production composition work.

## Critical regression locks

Do not leave or reintroduce:

- active composition with disabled required modules;
- Coordinator discarding concrete module output;
- production adapters referenced only by tests;
- Blueprint lifecycle state lost after restart;
- event projection without project/workspace isolation;
- retry events without durable payload/reference;
- source revision compared directly with Twin revision;
- completion while mandatory elements remain unsatisfied;
- Plan Compiler accepting dependency cycles;
- E2E claims based only on predetermined runner results;
- benchmark results based on manually supplied outcomes.

## Module boundaries

Public facades:

```text
DigitalTwinModule
ArchitectureBlueprintModule
ConvergenceModule
ProjectIntelligenceModule
```

Production must construct concrete Twin, Blueprint, and Convergence implementations behind these facades. Internal analyzers, stores, linkers, matchers, collectors, and policies remain private.

Forbidden dependencies include Planner or Generator reading private module stores, Convergence reading private Twin/Blueprint tables, Digital Twin writing PlanPool state, and portable modules importing FastAPI/UI/app APIs.

## Authority

- Requirement owns intent and constraints.
- Blueprint owns approved target design.
- Workspace/Git owns source.
- Digital Twin owns revisioned interpretation of actual source and observations.
- PlanPool owns execution state.
- Proposal owns generated patch artifacts.
- Safe Apply owns mutation.
- Verification/runtime owns observed outcomes.
- Convergence owns immutable reports and bounded advisory decisions.

Project Intelligence coordinates context and decisions. It is not mutation authority.

## Safety

Never bypass Requirement/decision gates, PlanPool authority, path and revision checks, Proposal/Safe Apply, command authority, bounded retry, rollback, project/workspace isolation, or truthful verification. `unavailable` is not `passed`.

Projection or refresh failure must not undo successful canonical work; record degraded state and retry work instead.

## Migration

Generate and maintain the real consumer registry. Use shadow comparison before cutover. Keep rollback available. Remove a legacy path only after consumer-zero, parity or documented superiority, data migration, rollback, and real E2E gates pass.

## Testing and evidence

Order:

```text
regression reproduction
-> component tests
-> facade/boundary tests
-> affected legacy tests
-> production integration
-> restart/fault tests
-> acceptance scenario
-> milestone suite
```

Record commands, exact results, durations, platform/runtime versions, relevant revisions, unavailable checks, and artifact references. Mocks may prove unit behavior only.

## Stop conditions

Stop only for an approval-required destructive migration, a safety/authority conflict, a required environment with no truthful alternative, or a critical architecture/security/data decision needing the existing decision gate.

Implementation size, test count, and remaining packages are not blockers.

## Completion

Do not mark the program complete before `PIR-15` and every live gate in the recovery master goal passes. Old PI status, synthetic runners, adapter-only tests, and manually supplied metrics are not substitutes for production wiring, real execution, rollout evidence, or retirement.
