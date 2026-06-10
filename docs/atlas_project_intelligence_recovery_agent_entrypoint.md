# Atlas Project Intelligence Recovery — Codex Goal Entrypoint

This is the canonical execution entrypoint for the active corrective track.

## Goal instruction

```text
Read AGENTS.md and execute the active Atlas Project Intelligence Recovery goal through completion.
Start from the package selected by docs/atlas_project_intelligence_recovery_current_status.md, initially PIR-0.
Treat PI-0 through PI-25 as the Foundation Track, not as proof of production completion.
Implement PIR packages sequentially, test at the required proof level, update recovery current status after every coherent slice, and continue automatically while acceptance criteria pass.
Do not stop at planning. Do not claim production connection from adapter-only tests, claim live E2E from injected success runners, or claim benchmark improvement from manually supplied metrics.
Do not push, merge, self-apply, weaken safety boundaries, or remove legacy paths before live migration gates pass.
```

## Read order

1. `AGENTS.md`
2. `docs/atlas_project_intelligence_recovery_master_goal.md`
3. `docs/atlas_project_intelligence_pi0_25_implementation_audit.md`
4. `docs/atlas_project_intelligence_recovery_current_status.md`
5. current PIR package in `docs/atlas_project_intelligence_recovery_implementation_plan.md`
6. relevant sections of `docs/atlas_project_intelligence_recovery_detailed_design.md`
7. relevant sections of `docs/atlas_project_intelligence_recovery_test_plan.md`
8. existing `atlas_project_intelligence_decisions.md`, contracts, architecture, migration plan, and old PI implementation documents as Foundation references
9. target files, public contracts, direct callers, dependencies, and related tests

## Execution loop

For the current PIR package:

1. verify the current status against current `main`;
2. reproduce the audited defect or missing production path;
3. inspect public contracts and real production callers;
4. implement the smallest coherent vertical slice;
5. preserve off/shadow/rollback behavior;
6. run focused and conformance tests;
7. run affected legacy tests;
8. run production integration and restart/fault tests required by the package;
9. run the package acceptance scenario;
10. record exact commands, results, unavailable checks, and evidence;
11. update recovery current status with the correct proof level;
12. continue automatically within the package until `acceptance_complete`, then advance.

## Proof-level discipline

Use these status levels only:

```text
not_started
in_progress
component_complete
production_connected
acceptance_complete
blocked
```

Examples:

- a concrete class plus unit tests may be `component_complete`;
- an adapter called by the real Atlas service may be `production_connected`;
- a package requiring a real workspace/build/restart is not `acceptance_complete` until that evidence exists.

Never convert unavailable evidence into passed evidence.

## Recovery priorities

The required dependency order is:

```text
truthful baseline
-> durable concrete modules
-> production composition
-> real Twin lifecycle/event/runtime loop
-> deep graph completion
-> durable Blueprint/Convergence correctness
-> Planner/PlanPool integration
-> Proposal/Safe Apply/refresh integration
-> Verification/recovery/resume integration
-> real Greenfield E2E
-> live rollout/platform/scale evidence
-> real comparative benchmark and retirement
```

Do not begin broad deep-graph rewrites before the concrete durable facade and production composition are working.

## Critical regression locks

Do not allow any of the following to remain or reappear:

- active factory using disabled required modules;
- coordinator discarding concrete module output;
- production adapters referenced only by tests;
- Blueprint lifecycle state lost after restart;
- event projection keyed only by project rather than project/workspace;
- source revision compared directly to Twin revision;
- completion from one verified element while mandatory elements remain unverified;
- Plan Compiler silently accepting dependency cycles;
- Greenfield E2E using only predetermined runner results;
- benchmark results created from manually supplied outcome metrics.

## Safety and authority

Never bypass:

- Requirement, clarification, and critical-decision authority;
- PlanPool/workflow authority;
- Proposal and Safe Apply boundaries;
- base/source revision preconditions;
- command allowlists and sandboxing;
- canonical verification truth;
- bounded retry and rollback;
- project/workspace isolation;
- direct push, merge, and self-apply restrictions.

Project Intelligence remains orchestration/context/advisory logic. It does not gain mutation authority.

## Evidence update template

After every coherent slice, update recovery current status with:

```text
Package and proof level
Commit/PR
Changed modules/files
Defect reproduced and corrected
Production callers connected
Commands and exact results
Restart/fault results
Real fixture/environment evidence
Unavailable checks
Safety invariants
Rollout/migration state
Known limitations
Next slice/package
Blocker, if any
```

## Stop conditions

Stop only when:

- a destructive migration requires user approval;
- proceeding requires weakening a safety or authority boundary;
- a real required environment is unavailable and the package has no truthful alternative path;
- a critical architecture/security/data-loss decision cannot be represented by the existing decision gate.

Implementation size, number of tests, context length, and remaining packages are not blockers.

## Completion

Do not mark the program complete before PIR-15 and every live gate in the recovery master goal passes. The old PI-25 helper and status are not substitutes for a real production benchmark, active rollout, or legacy retirement.
