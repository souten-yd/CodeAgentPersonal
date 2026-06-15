# Atlas Twin / Forge / Git Steward — Current Status

Status: initial implementation slice in progress.

This file is the mutable checkpoint for the approved integration of Project Intelligence, Project Digital Twin, Genesis/Greenfield, Forge Execution Policy, and Atlas Git Steward.

## Program state

- Overall: `component_complete` for the initial contracts/policy, Instruction Compiler, Genesis taxonomy, No-Data Bootstrap Gate, and Interface First Generator slices; broader program remains `not_started` beyond TFG-1/2/3/3A/4/4A foundations
- Current package: Package 2A No-Data Bootstrap Gate and Interface First Generator completed at component level
- Current proof level: `component_complete` for contracts, ExecutionPolicy selector, TwinBrief compiler, Git Steward authority classifier, Instruction Compiler, Genesis classifier/Greenfield adapter, No-Data Bootstrap Gate, and Interface First Generator; `contract_present` for completed goal-mode execution instructions
- Blocker: real LLM and real runtime evidence not collected for these component slices
- Rollout: not connected; future implementation must use off/shadow/active semantics
- Remote publication rule: local Git operations are autonomous; remote publication requires user approval

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_twin_forge_git_steward_master_goal.md`
3. `docs/atlas_twin_forge_git_steward_detailed_plan.md`
4. `docs/atlas_twin_forge_git_steward_goal_mode_execution.md`
5. `docs/atlas_twin_forge_git_steward_agent_entrypoint.md`
6. this file
7. existing Project Intelligence / Twin / Greenfield / Forge files

## Current implementation assessment

### Strongly reusable existing code

- Project Intelligence contracts, coordinator, production factory, and rollout model.
- Project Twin concrete module, source snapshot, static/behavioral graph, impact query, runtime evidence promotion.
- Greenfield orchestrator, state machine, and E2E harness.
- Forge route taxonomy and route matrix.

### Existing code now extended in this PR

- Generation context can feed `compile_generation_twin_brief(...)`.
- Forge route selection can feed `ExecutionPolicySelector`.
- Git local/remote authority is represented by `classify_git_operation(...)`.
- Initial tests cover route safety, model-sensitive injection, TwinBrief compilation, and Git authority boundaries.
- Goal-mode execution instructions now define the end-to-end implementation package sequence through active rollout and real LLM/runtime closure.
- Goal-mode instructions explicitly include No-Data Bootstrap Gate, Interface First Generator, Schema Guardian, StateMirror, Anti-Pattern Memory, Golden Patch Retrieval, and Skill Distiller.

### Still required

- Instruction Compiler component implementation now exists; shadow integration still required.
- Interface First Generator component implementation now exists; shadow integration still required.
- Genesis taxonomy component implementation now exists; Integration Impact Gate and broader Genesis shadow integration still required.
- No-Data Bootstrap Gate component implementation now exists; shadow integration still required.
- BlastMap and Contract Sentinel.
- Schema Guardian and StateMirror.
- TwinProof and Assumption Breaker.
- Git Steward concrete command adapters.
- Patch/Integration/Flag/Merge Impact Gates.
- Proof Ledger and Repair Compass.
- Anti-Pattern Memory.
- Forge model capability profile persistence/eval packs.
- Golden Patch Retrieval and Skill Distiller.
- Real LLM/runtime evaluation harness.
- Atlas pipeline shadow/active integration.

## Planned package table

| Package | Title | Target proof level | Status |
|---|---|---|---|
| TFG-0 | Audit and consolidation map | contract_present | partial_in_pr |
| TFG-1 | Twin Control Plane contracts | component_complete | partial_in_pr |
| TFG-2 | Forge Execution Policy Matrix | component_complete | partial_in_pr |
| TFG-3 | TwinBrief and Instruction Compiler | shadow_connected | instruction_compiler_component_complete |
| TFG-3A | Interface First Generator | shadow_connected | interface_first_component_complete |
| TFG-4 | Genesis integration | shadow_connected | genesis_taxonomy_component_complete |
| TFG-4A | No-Data Bootstrap Gate | shadow_connected | no_data_bootstrap_component_complete |
| TFG-5 | BlastMap and Contract Sentinel | shadow_connected | not_started |
| TFG-5A | Schema Guardian | shadow_connected | not_started |
| TFG-5B | StateMirror | shadow_connected | not_started |
| TFG-6 | TwinProof and Assumption Breaker | shadow_connected | not_started |
| TFG-7 | Git Steward MVP | shadow_connected | authority_contract_partial_in_pr |
| TFG-8 | Patch/Integration/Flag/Merge gates | shadow_connected | not_started |
| TFG-9 | Proof Ledger and Repair Compass | production_connected | not_started |
| TFG-9A | Anti-Pattern Memory | production_connected | not_started |
| TFG-10 | Forge profile store, eval packs, Golden Patch Retrieval, Skill Distiller | real_llm_evaluated | not_started |
| TFG-11 | Atlas pipeline shadow integration | shadow_connected | not_started |
| TFG-12 | Active rollout and acceptance | acceptance_complete | not_started |
| TFG-13 | Real LLM and real runtime evaluation closure | real_llm_evaluated / real_runtime_evaluated | not_started |

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
- Schema changes are not accepted without compatibility/migration proof.
- Backend/UI/persistence/runtime state disagreements are not hidden.
- Retrieved golden patches and distilled skills remain advisory and evidence-bound.

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

## Initial implementation record

```text
Work package: TFG initial contracts/policy slice + completed goal-mode handoff
Status: partial_in_pr
Proof level: component_complete for pure contracts/policies only; contract_present for completed goal-mode instructions
Commit/PR: PR #1859 branch atlas/twin-forge-git-steward-plan
Changed modules/files:
- agent/twin_control_plane/__init__.py
- agent/twin_control_plane/contracts.py
- agent/twin_control_plane/twin_brief.py
- agent/model_forge/execution_policy.py
- agent/git_steward/__init__.py
- agent/git_steward/contracts.py
- tests/test_twin_forge_git_steward_initial.py
- docs/atlas_twin_forge_git_steward_*.md
Executed commands and exact results: not run in this connector-only update; tests were authored for future CI/local execution
Real LLM evidence: not collected in this PR
Real runtime evidence: not collected in this PR
Unavailable checks: real LLM/runtime evaluation intentionally remains pending until execution harness packages
Adversarial tests:
- unsafe micro route request for large change
- weak model flag reasoning weakness requires FeatureFlagBaseline
- local Git operations allowed while remote publication requires approval
- sensitive/large artifact ignore patterns present
- goal-mode instructions now require schema drift, StateMirror, no-data, and retrieved-patch adversarial cases
Safety invariants checked:
- RouteMatrix remains the route authority
- remote publication remains approval-bound
- stale-test deletion policy is represented as a hard constraint
- Safe Apply boundary is represented as a hard constraint
Known limitations:
- no Atlas pipeline integration yet
- no concrete Git command execution adapter yet
- no real LLM/runtime evaluation yet
- no Genesis/BlastMap/TwinProof/ProofLedger implementation yet
- no Schema Guardian/StateMirror/No-Data/InterfaceFirst implementation yet
- no Anti-Pattern Memory/Golden Patch Retrieval/Skill Distiller implementation yet
Next package: Package 0 in goal-mode execution instructions: verify initial slice and record exact test output
Blocker: none
```

```text
Work package: Package 1 Instruction Compiler + Package 2 Genesis taxonomy + Package 2A No-Data Bootstrap Gate and Interface First Generator
Status: component_complete for pure instruction, Genesis classification, no-data bootstrap, and interface-first controls; shadow integration not started
Proof level: component_complete for DTO/policy behavior only
Commit/PR: local branch codex/tfg-instruction-interface; remote publication requested by user
Changed modules/files:
- agent/twin_control_plane/instruction_compiler.py
- agent/twin_control_plane/genesis.py
- agent/twin_control_plane/no_data_bootstrap_gate.py
- agent/twin_control_plane/interface_first_generator.py
- agent/twin_control_plane/__init__.py
- tests/test_twin_control_plane_instruction_compiler.py
- tests/test_twin_control_plane_genesis.py
- tests/test_twin_control_plane_no_data_interface_first.py
- docs/atlas_twin_forge_git_steward_current_status.md
Executed commands and exact results:
- `python -m pytest -q tests/test_twin_forge_git_steward_initial.py tests/test_twin_control_plane_instruction_compiler.py tests/test_twin_control_plane_genesis.py tests/test_twin_control_plane_no_data_interface_first.py` -> 24 passed in 3.75s.
- `python -m py_compile agent\twin_control_plane\instruction_compiler.py agent\twin_control_plane\genesis.py agent\twin_control_plane\no_data_bootstrap_gate.py agent\twin_control_plane\interface_first_generator.py agent\twin_control_plane\__init__.py` -> passed.
Real LLM evidence:
- Not collected for this PR; these slices are pure component DTO/policy helpers and are not connected to Atlas runtime/shadow/active execution.
Real runtime evidence:
- Not collected; no Atlas runtime path is active in this PR.
Unavailable checks:
- Real runtime/Portal evidence is unavailable/not applicable for these pure component slices.
- Real LLM advisory review was not collected for these non-runtime component slices.
Adversarial tests:
- Weak-local and frontier-assisted instructions preserve hard constraints and approval boundaries.
- Audit-only instructions do not imply mutation authority.
- Empty and partially-known projects require bootstrap proof instead of assuming prior data.
- Interface-first plans emit interface/schema/state/test contracts before implementation steps.
- Greenfield session adaptation preserves Safe Apply slice behavior.
Safety invariants checked:
- Project Intelligence and Project Twin remain advisory/context inputs, not execution authority.
- Interface First Generator feeds TwinBrief and does not execute, apply, verify, commit, or publish.
- Unavailable evidence is not converted into passed evidence.
- Remote publication remains approval-bound and is only occurring because the user explicitly requested PR creation and merge.
Known limitations:
- These components are not wired into Atlas shadow/active execution.
- Integration Impact Gate, BlastMap, Contract Sentinel, Schema Guardian, StateMirror, TwinProof, Git Steward local adapter, Patch Impact Gate, Proof Ledger, Repair Compass, Anti-Pattern Memory, Forge profile store, and runtime/model closure remain future PRs.
Next package: Package 3 Integration Impact Gate.
Blocker, if any: none for local component work.
```
