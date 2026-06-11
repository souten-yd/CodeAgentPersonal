# Atlas Project Intelligence Recovery — Agent Instructions

The active implementation track is `PIR-0..PIR-15`.

`PDT-0..PDT-14` remain Project Digital Twin Core v1 history. `PI-0..PI-25` remain the Foundation Track: useful contracts, helpers, and tests, but not proof that the production loop is complete. Do not restart or delete them.

## Additional approved goal: Atlas Portal + Model Forge

The Portal + Model Forge program is approved as a separate implementation track selected by `docs/atlas_portal_forge_current_status.md` and defined by:

```text
docs/atlas_portal_forge_master_goal.md
docs/atlas_portal_forge_detailed_design.md
docs/atlas_portal_forge_implementation_plan.md
docs/atlas_portal_forge_test_plan.md
docs/atlas_portal_forge_agent_entrypoint.md
```

Use the Portal + Model Forge goal when the task explicitly asks for Forge, model routing, OpenRouter, Arena, Skill Radar, Portal polish, Portal x Forge integration, Capsule replay/profile feedback, or legacy model orchestrator retirement. Do not confuse this with PIR completion. PIR remains active until its own current status and live gates complete.

Portal baseline facts for the Forge track:

- Portal / Play / Capsule PR-PPC-0 through PR-PPC-12 are already complete.
- Portal UI reconciliation already wired Portal navigation, catalog/run sheet, Save/Snapshot/Discard, Export, Fork to Atlas, Uninstall, Delete Data, and Capsule builder UI.
- Do not restart Portal from scratch. Only implement remaining Portal polish and Portal x Forge trace work.

Forge safety facts:

- OpenRouter is one Forge Provider, not a special hard-coded execution path.
- External model use must be gated by Source Mode and privacy policy.
- Local Only must not call OpenRouter or any external provider.
- Arena candidates must never be directly applied. Candidate adoption must go through Proposal, Safe Apply, Verification, and, when runnable, Portal.
- The legacy model execution/orchestration path must be wrapped as a Legacy Executor and kept as primary until shadow/cutover evidence passes.
- Do not delete legacy model paths before retirement gates.

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

For Portal + Model Forge tasks, use this read order after reading `AGENTS.md`:

1. `docs/atlas_portal_forge_master_goal.md`
2. `docs/atlas_portal_forge_current_status.md`
3. current package in `docs/atlas_portal_forge_implementation_plan.md`
4. relevant sections of `docs/atlas_portal_forge_detailed_design.md`
5. relevant sections of `docs/atlas_portal_forge_test_plan.md`
6. `docs/atlas_play_portal_capsule_current_status.md` when touching Portal/Capsule/Play
7. Project Intelligence Recovery docs when touching Atlas/PlanPool/Proposal/Safe Apply/Verification/Convergence
8. target code, public contracts, direct callers, dependencies, and tests

## Goal instruction

```text
Read AGENTS.md and execute the active Atlas Project Intelligence Recovery goal through completion.
Start from the package selected by docs/atlas_project_intelligence_recovery_current_status.md, initially PIR-0.
Treat PI-0 through PI-25 as the Foundation Track, not as proof of production completion.
Implement PIR packages sequentially, test at the required proof level, update recovery current status after every coherent slice, and continue automatically while acceptance criteria pass.
Do not stop at planning. Do not claim production integration from adapter-only tests, live E2E from injected success runners, or benchmark improvement from manually supplied metrics.
Do not weaken safety boundaries or remove legacy paths before migration gates pass.
```

Portal + Model Forge goal instruction:

```text
Read AGENTS.md and execute the Atlas Portal + Model Forge goal through completion.
Start from the package selected by docs/atlas_portal_forge_current_status.md.
Portal is already implemented through PR-PPC-12 plus UI reconciliation; do not restart it from scratch.
Implement PFG packages sequentially, update docs/atlas_portal_forge_current_status.md after every coherent slice, and continue automatically while acceptance criteria pass.
Use PIR-style proof levels and evidence discipline.
Do not claim live model, Portal runtime, OpenRouter, benchmark, cutover, or retirement evidence unless it actually ran.
Keep Forge off by default until each stage has shadow/cutover evidence.
Do not delete legacy model execution paths before retirement gates pass.
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

For Portal + Model Forge, mock provider tests prove provider component behavior only. Real local/self-hosted model execution, real Portal run evidence, optional OpenRouter live smoke, and stage cutover evidence are separate proof levels. UI rendering alone never proves Portal runtime or model quality.

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

For Portal + Model Forge packages, also:

- preserve existing Portal Save/Snapshot/Discard/Capsule/Export/Fork behavior;
- preserve data-free package export;
- preserve no free-form command execution;
- preserve external provider disabled-by-default behavior;
- preserve `unavailable` distinct from `passed`;
- record real model/Portal/OpenRouter evidence only when actually executed.

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

Portal + Model Forge dependency order:

```text
Portal polish audit
-> Portal upload/snapshot/legacy manifest polish
-> Forge schemas and provider registry
-> Legacy Executor adapter
-> local/OpenRouter providers
-> benchmark presets
-> Arena and Candidate Evaluator
-> Model Profile Store
-> Stage/Route Matrix
-> Forge API and UI
-> Portal x Forge trace/evidence integration
-> real local-model preset evidence
-> optional OpenRouter live smoke
-> stage shadow evidence
-> controlled Forge cutover
-> legacy retirement gates
```

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

Portal + Model Forge must not leave or introduce:

- Portal package export bundling runtime data by default;
- browser/import path traversal;
- direct temporary port exposure outside session-owned gateway/proxy policy;
- free-form command fields;
- Arena direct apply;
- external provider calls in Local Only mode;
- persisted or logged API secrets;
- mock OpenRouter results claimed as live OpenRouter evidence;
- legacy model path deletion before retirement evidence;
- complex always-visible UI matrices that make normal use difficult.

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

Portal + Forge boundaries:

```text
Portal owns execution/artifact/data lifecycle.
Forge owns provider/model/route evaluation and selection.
Atlas owns requirement/plan/proposal/Safe Apply/verification/convergence.
```

Forge provider modules must not import UI modules. UI modules must call Forge APIs instead of importing provider internals. Portal may record Forge trace metadata but must not become a model selector.

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

For Portal + Forge:

- Forge owns model/provider/route recommendation and candidate evaluation.
- Portal owns runtime execution and generated data lifecycle.
- Capsule owns immutable package projection.
- Candidate output owns nothing until converted into Proposal and applied by Safe Apply.

## Safety

Never bypass Requirement/decision gates, PlanPool authority, path and revision checks, Proposal/Safe Apply, command authority, bounded retry, rollback, project/workspace isolation, or truthful verification. `unavailable` is not `passed`.

Projection or refresh failure must not undo successful canonical work; record degraded state and retry work instead.

## Migration

Generate and maintain the real consumer registry. Use shadow comparison before cutover. Keep rollback available. Remove a legacy path only after consumer-zero, parity or documented superiority, data migration, rollback, and real E2E gates pass.

For Forge replacing legacy model orchestration, use this sequence per stage:

```text
legacy primary
-> Forge shadow
-> Forge primary with legacy fallback
-> Forge primary only
-> legacy retired
```

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

Portal + Forge evidence must explicitly separate:

```text
mock provider evidence
local provider evidence
real configured model evidence
Portal runtime evidence
Capsule replay evidence
OpenRouter mock evidence
OpenRouter live smoke evidence
stage shadow/cutover evidence
legacy retirement evidence
```

## Stop conditions

Stop only for an approval-required destructive migration, a safety/authority conflict, a required environment with no truthful alternative, or a critical architecture/security/data decision needing the existing decision gate.

Implementation size, test count, and remaining packages are not blockers.

For Portal + Forge, broad legacy deletion, changing default external-code exposure, or making cloud providers mandatory requires explicit approval.

## Completion

Do not mark the PIR program complete before `PIR-15` and every live gate in the recovery master goal passes. Old PI status, synthetic runners, adapter-only tests, and manually supplied metrics are not substitutes for production wiring, real execution, rollout evidence, or retirement.

Do not mark Portal + Model Forge complete before `PFG-38` and every required gate in `docs/atlas_portal_forge_master_goal.md` passes. Docs-only setup, mock provider tests, UI rendering, unavailable OpenRouter/local model checks, or Arena-only candidate generation are not substitutes for real Portal/model evidence and controlled cutover evidence.
