# Atlas Twin / Forge / Git Steward — Current Status

Status: `not_started` for implementation, `contract_present` for planning documents.

This file is the mutable checkpoint for the approved integration of Project Intelligence, Project Digital Twin, Genesis/Greenfield, Forge Execution Policy, and Atlas Git Steward.

## Program state

- Overall: `not_started`
- Current package: planning handoff
- Current proof level: `contract_present`
- Blocker: implementation not started
- Rollout: not connected; future implementation must use off/shadow/active semantics
- Remote publication rule: local Git operations are autonomous; remote publication requires user approval

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_twin_forge_git_steward_master_goal.md`
3. `docs/atlas_twin_forge_git_steward_detailed_plan.md`
4. `docs/atlas_twin_forge_git_steward_agent_entrypoint.md`
5. this file
6. existing Project Intelligence / Twin / Greenfield / Forge files

## Current implementation assessment

### Strongly reusable existing code

- Project Intelligence contracts, coordinator, production factory, and rollout model.
- Project Twin concrete module, source snapshot, static/behavioral graph, impact query, runtime evidence promotion.
- Greenfield orchestrator, state machine, and E2E harness.
- Forge route taxonomy and route matrix.

### Existing code to extend

- Generation context should feed TwinBrief Compiler.
- Impact query should feed BlastMap.
- Runtime evidence should feed TwinProof and Proof Ledger.
- Greenfield partial mode should become Feature Genesis semantics.
- Forge route selection should feed ExecutionPolicy, not own injection policy directly.

### New code required

- Twin Control Plane contracts.
- TwinBrief and Instruction Compiler.
- Genesis taxonomy and Integration Impact Gate.
- BlastMap and Contract Sentinel.
- TwinProof and Assumption Breaker.
- Git Steward.
- Patch/Integration/Flag/Merge Impact Gates.
- Proof Ledger and Repair Compass.
- Forge Execution Policy Matrix and model capability profiler.
- Real LLM/runtime evaluation harness.

## Planned package table

| Package | Title | Target proof level | Status |
|---|---|---|---|
| TFG-0 | Audit and consolidation map | contract_present | not_started |
| TFG-1 | Twin Control Plane contracts | component_complete | not_started |
| TFG-2 | Forge Execution Policy Matrix | component_complete | not_started |
| TFG-3 | TwinBrief and Instruction Compiler | shadow_connected | not_started |
| TFG-4 | Genesis integration | shadow_connected | not_started |
| TFG-5 | BlastMap and Contract Sentinel | shadow_connected | not_started |
| TFG-6 | TwinProof and Assumption Breaker | shadow_connected | not_started |
| TFG-7 | Git Steward MVP | shadow_connected | not_started |
| TFG-8 | Patch/Integration/Flag/Merge gates | shadow_connected | not_started |
| TFG-9 | Proof Ledger and Repair Compass | production_connected | not_started |
| TFG-10 | Real LLM and real runtime evaluation | real_llm_evaluated / real_runtime_evaluated | not_started |
| TFG-11 | Atlas pipeline shadow integration | shadow_connected | not_started |
| TFG-12 | Active rollout and acceptance | acceptance_complete | not_started |

## Safety invariants

- Safe Apply remains the file mutation boundary.
- Approval gates remain intact.
- Project isolation remains intact.
- Existing off mode preserves current behavior.
- Shadow mode produces evidence without changing behavior.
- Active mode requires prior shadow evidence.
- Local Git operations are allowed without approval.
- Remote publication requires approval.
- Stale tests are not auto-deleted.
- Tests and gates are not weakened to pass.
- Unavailable real LLM/runtime checks are reported as unavailable.

## Evidence requirements

A package may not reach `acceptance_complete` from unit tests alone. Required evidence depends on package scope:

- contract tests for DTOs and policy boundaries;
- integration tests for the intended execution path;
- adversarial tests;
- real LLM evidence for model-facing behavior;
- real runtime evidence for generation, Genesis, Portal, or Git Steward behavior;
- exact command outputs;
- unavailable checks recorded truthfully.

## Status update template

```text
Work package:
Status:
Proof level:
Commit/PR:
Changed modules/files:
Executed commands and exact results:
Real LLM evidence:
Real runtime evidence:
Unavailable checks:
Adversarial tests:
Safety invariants checked:
Known limitations:
Next package:
Blocker, if any:
```

## Initial planning record

```text
Work package: planning handoff
Status: proposed
Proof level: contract_present
Commit/PR: pending PR
Changed modules/files:
- docs/atlas_twin_forge_git_steward_master_goal.md
- docs/atlas_twin_forge_git_steward_detailed_plan.md
- docs/atlas_twin_forge_git_steward_agent_entrypoint.md
- docs/atlas_twin_forge_git_steward_current_status.md
Executed commands and exact results: documentation-only GitHub write through connector
Real LLM evidence: not applicable for planning handoff
Real runtime evidence: not applicable for planning handoff
Unavailable checks: implementation not started
Adversarial tests: specified in detailed plan, not yet implemented
Safety invariants checked: no production code changed; no rollout changed; no remote release/merge requested
Known limitations: this PR only records goal, plan, and implementation instructions
Next package: TFG-0 Audit and consolidation map
Blocker: none
```
