# Atlas Twin / Forge / Git Steward — Detailed Implementation Plan

Status: proposed detailed plan.

This plan implements the approved integration of Project Intelligence, Project Digital Twin, Genesis/Greenfield, Forge route/model evaluation, and local Git development management.

Default strategy: reuse first, consolidate second, replace only when existing code cannot satisfy the required contract.

## 1. Existing implementation to reuse

### Project Intelligence

Reuse the existing coordinator, production factory, rollout semantics, and public contract style:

- `agent/project_intelligence/contracts.py`
- `agent/project_intelligence/coordinator.py`
- `agent/project_intelligence/production_factory.py`
- `agent/project_intelligence/rollout.py`

Project Intelligence remains contextual and advisory. Safe Apply, approval, verification, Git publication, and rollback remain separate authorities.

### Project Digital Twin

Reuse the concrete Twin implementation and source/runtime evidence capabilities:

- `agent/project_twin/module.py`
- `agent/project_twin/query/impact.py`
- `agent/project_twin/store.py`
- static and behavioral graph analyzers
- runtime evidence promotion into durable Twin facts

New components should use Twin query/context APIs where possible instead of duplicating repository analysis.

### Greenfield / Genesis

Reuse the existing Greenfield orchestrator and state machine:

- `agent/project_intelligence/greenfield.py`
- `agent/project_intelligence/greenfield_state_machine.py`
- `agent/project_intelligence/greenfield_e2e.py`

Do not create a separate Greenfield pipeline. Reclassify it under Genesis:

- Project Genesis: empty project generation.
- Feature Genesis: new capability inside an existing project.
- Module Genesis: new API/service/UI/test cluster.

`greenfield_partial` should be normalized into Feature Genesis semantics where practical.

### Forge

Reuse the existing route taxonomy and route matrix:

- `agent/model_forge/route_taxonomy.py`
- `agent/model_forge/route_matrix.py`

Keep route selection responsible only for execution route selection. Add a separate Execution Policy layer above it.

## 2. New modules

### `agent/twin_control_plane/`

Add a new integration layer that compiles Twin/PI context into model-specific instructions and gates.

Proposed files:

- `contracts.py`
- `twin_brief.py`
- `instruction_compiler.py`
- `genesis.py`
- `blast_map.py`
- `contract_sentinel.py`
- `twinproof.py`
- `assumption_breaker.py`
- `patch_impact_gate.py`
- `integration_impact_gate.py`
- `merge_impact_gate.py`
- `flag_impact_matrix.py`
- `proof_ledger.py`
- `repair_compass.py`

Initial MVP should use small, composable DTO and pure-policy modules. Avoid a monolithic service until contracts are stable.

### `agent/model_forge/` additions

Add model capability and execution policy components above the existing route matrix:

- `model_capability_profile.py`
- `injection_policy.py`
- `instruction_policy.py`
- `execution_policy.py`
- `execution_policy_matrix.py`
- `eval_packs.py`
- `capability_scoring.py`
- `profile_store.py`

### `agent/git_steward/`

Add local Git development management. Local operations are autonomous; remote publication requires approval.

- `contracts.py`
- `detector.py`
- `initializer.py`
- `ignore_policy.py`
- `branch_manager.py`
- `worktree_manager.py`
- `diff_service.py`
- `commit_service.py`
- `rollback_service.py`
- `remote_service.py`
- `safety.py`
- `proof_adapter.py`

Remote GitHub PR/push integration must remain behind explicit approval.

## 3. Core contracts

### ExecutionPolicy

Represents the final decision for a task:

- route
- model id or model role
- instruction style
- model capability mode
- Twin injection level
- required Twin modules
- required gates
- Git policy
- hard constraints
- advisory context
- reasons
- confidence

### Injection levels

- 0: no assist except hard safety rules
- 1: brief summary only
- 2: contracts plus impact summary
- 3: allowed/forbidden refs plus required tests and proof requirements
- 4: interface skeleton plus stepwise repair and strict gates

### Instruction styles

- `freeform_design`
- `constrained_patch`
- `interface_first`
- `test_first`
- `assumption_breaker`
- `repair_compass`
- `blueprint_slice`
- `patch_dsl`
- `audit_only`

### Model capability modes

- `weak_local`
- `standard`
- `frontier_assisted`
- `audit_only`

### Git policy

- local repo required
- auto init allowed
- baseline commit required
- local branch required
- worktree preferred
- local commit required
- fetch/pull allowed
- remote publication requires approval

## 4. Implementation phases

### Phase 0 — Audit and consolidation map

Deliverables:

- `docs/atlas_twin_forge_git_steward_current_status.md`
- inventory of reused modules, extended modules, and replace candidates
- explicit list of components that must not be deleted

Acceptance:

- Documents current implementation without claiming completion from design docs alone.
- Identifies production-connected vs scaffold-only components.

### Phase 1 — Contracts and pure policies

Deliverables:

- Twin Control Plane contract DTOs.
- Forge ExecutionPolicy DTOs.
- Git Steward authority contracts.
- Unit tests for schema stability and forbidden states.

Acceptance:

- Contract tests pass.
- Contract modules do not import FastAPI, UI, app APIs, private stores, or heavyweight runtime code.

### Phase 2 — Forge Execution Policy Matrix

Deliverables:

- selector that consumes ChangeClass, ForgeRoute, model capability profile, task category, and Twin risk summary;
- returns ExecutionPolicy;
- preserves RouteMatrix as route-only authority.

Acceptance:

- Critical/large route safety still overrides unsafe requested micro routes.
- Weak models receive higher injection for weak capabilities.
- Frontier-assisted models receive low/medium injection and Twin Challenge where allowed.
- Route injection compatibility prevents contradictory choices.

### Phase 3 — TwinBrief and Instruction Compiler

Deliverables:

- compile Project Intelligence PlanningContextPackage and GenerationContextPackage into TwinBrief;
- compile TwinBrief plus ExecutionPolicy into model-facing implementation instructions.

Acceptance:

- Weak-local instructions include allowed/forbidden refs, interface skeleton when required, tests, and proof requirements.
- Frontier-assisted instructions preserve design freedom, hard constraints, advisory context, and Twin Challenge form.
- Audit-only instructions minimize pre-generation constraints and strengthen post-generation gates.

### Phase 4 — Genesis integration

Deliverables:

- Project/Feature/Module Genesis taxonomy;
- adapter from existing Greenfield sessions to Genesis runs;
- Feature Genesis flow combining Existing Project Twin, Feature Genesis Twin, and Integration Impact Gate.

Acceptance:

- Existing Greenfield Safe Apply slice behavior remains intact.
- Feature Genesis does not become a separate pipeline.
- Integration Impact Gate reports existing integration points, contract risks, test needs, and proof requirements.

### Phase 5 — BlastMap and Contract Sentinel MVP

Deliverables:

- BlastMap built from existing Twin impact query and context package;
- Contract Sentinel for hard safety and contract-preservation checks.

Acceptance:

- Impact confidence is advisory unless classified as a hard safety contract.
- Approval and Safe Apply boundaries are protected.
- Test weakening and stale-test deletion are hard failures unless explicitly approved and proven safe.

### Phase 6 — TwinProof and Assumption Breaker MVP

Deliverables:

- Test inventory over runtime observations and related tests;
- impacted/stale/redundant/flaky/coverage-gap classifications;
- retirement candidate policy;
- Assumption Breaker brief generator.

Acceptance:

- Stale tests are never auto-deleted; they become retirement candidates.
- Missing reload/persistence/feature-flag/no-data/UI-projection tests are surfaced.
- Failure classification distinguishes product regression, stale test contract, missing mock, environment unavailable, and insufficient evidence.

### Phase 7 — Git Steward MVP

Deliverables:

- local repo detection;
- auto local git init when absent;
- ignore-file hardening;
- baseline commit;
- Atlas branch/worktree management;
- local diff, commit, rollback;
- proof adapter writing branch/commit/diff refs.

Acceptance:

- Local operations do not require approval.
- Remote publication or remote mutation requires approval.
- Dirty user work is not destroyed.
- Sensitive files, model weights, build outputs, runtime data, and cache directories are excluded before baseline commit.
- Rollback is limited to Atlas-owned branch/worktree/commits by default.

### Phase 8 — Patch, Integration, Flag, Merge gates

Deliverables:

- Patch Impact Gate comparing before/after Twin/diff/evidence;
- Integration Impact Gate for Feature Genesis;
- Flag Impact Matrix;
- Merge Impact Gate for base/feature/merged comparison.

Acceptance:

- Patch gates run after local commit and Twin refresh.
- Feature flag off baseline is required when a flag is added or changed.
- Merge gate reports schema/API/state/flag/test conflicts without auto-merging.

### Phase 9 — Proof Ledger and Repair Compass

Deliverables:

- Proof Ledger entries linking requirement, plan item, execution policy, Git branch/commit/diff, Twin revision, tests, runtime evidence, and gate decisions;
- Repair Compass generating minimal repair instructions from gate failures.

Acceptance:

- Proof Ledger can explain why a change is accepted or blocked.
- Repair Compass forbids test weakening, gate weakening, approval-boundary weakening, and unrelated broad rewrites.

### Phase 10 — Real LLM and real runtime evaluation

Deliverables:

- Forge eval packs for route/model/injection/style combinations;
- local LLM evaluation path;
- stronger/frontier-assisted evaluation path when configured;
- real runtime build/test/run evaluation for representative generated or modified project.

Acceptance:

- Results record exact model, route, instruction style, injection level, prompt/brief refs, outputs, tests, runtime observations, and failure classifications.
- Synthetic tests alone cannot close acceptance.
- If a real LLM or runtime is unavailable, status remains unavailable/pending, not passed.

## 5. Adversarial test requirements

Required adversarial cases:

1. Model requests unsafe micro route for large/critical change.
2. Frontier model challenges Twin incorrectly and tries to skip hard constraints.
3. Weak model omits feature flag off baseline test.
4. Model deletes stale test instead of marking retirement candidate.
5. Model weakens a failing test or gate.
6. Dirty working tree exists before pull/branch creation.
7. Git repo absent and project contains files that should not be committed.
8. Remote push/PR is attempted without approval.
9. Greenfield/Genesis attempts direct workspace write instead of Safe Apply.
10. Patch passes unit tests but fails Patch Impact Gate due to missing proof or contract drift.
11. Merge introduces flag/schema conflict across base/feature/merged Twins.
12. Real runtime unavailable is incorrectly reported as passed.

## 6. Integration-first development rule

Each package must include at least one focused unit test and one integration-oriented test. Later packages must include the representative path they serve:

ExecutionPolicy -> Git branch/worktree -> TwinBrief -> Instruction -> Safe Apply -> local commit -> Twin refresh -> Patch/TwinProof gates -> Proof Ledger.

Small slices are preferred, but a slice is not complete until its intended integration path succeeds.

## 7. Rollout policy

Use the existing rollout pattern:

- off: existing behavior unchanged
- shadow: produce ExecutionPolicy/TwinBrief/Git plan/TwinProof reports but do not alter execution behavior
- active: use ExecutionPolicy/TwinBrief/Git Steward/Gates in execution

Shadow evidence must be recorded before active rollout.

## 8. Status update template

After every package, update current status with:

- Work package
- Status
- Proof level
- Commit/PR
- Changed modules/files
- Executed commands and exact results
- Real LLM evidence
- Real runtime evidence
- Unavailable checks
- Adversarial tests
- Safety invariants checked
- Known limitations
- Next package
- Blocker, if any
