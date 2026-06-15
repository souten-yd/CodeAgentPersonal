# Atlas Twin / Forge / Git Steward — Goal Mode Execution Instructions

Status: implementation execution guide.

Use this document as the goal-mode handoff for finishing the Twin / Forge / Git Steward program. It is written for implementation agents that can modify the local repository, run tests, use configured local models, and iterate until the integration path succeeds.

## Goal

Finish the Atlas Twin / Forge / Git Steward program so Atlas can choose, for each development task:

1. Forge route;
2. model or model role;
3. Twin assistance level;
4. implementation instruction style;
5. local Git policy;
6. required gates and evidence;
7. proceed / repair / approval-needed decision.

Target path:

```text
User task
  -> ChangeClass and task category
  -> Forge RouteMatrix
  -> ModelCapabilityProfile
  -> ExecutionPolicy
  -> local Git branch/worktree plan
  -> Project Intelligence context
  -> TwinBrief
  -> model-specific instruction
  -> LLM output
  -> Proposal / Safe Apply
  -> local commit
  -> Twin refresh
  -> Patch Impact Gate
  -> TwinProof
  -> Proof Ledger
  -> optional external publication only after approval
```

## Required read order

1. `AGENTS.md`
2. `docs/atlas_twin_forge_git_steward_master_goal.md`
3. `docs/atlas_twin_forge_git_steward_detailed_plan.md`
4. `docs/atlas_twin_forge_git_steward_agent_entrypoint.md`
5. `docs/atlas_twin_forge_git_steward_current_status.md`
6. this file
7. existing Project Intelligence, Project Twin, Greenfield, Forge, and Git-related code/tests

## Core principle

Reuse existing code first.

Prefer extending/adapting:

- Project Intelligence contracts and coordinator;
- Project Twin module and impact query;
- Greenfield orchestrator and state machine;
- Forge route taxonomy and route matrix;
- existing rollout/off/shadow/active patterns.

Only replace code when it cannot satisfy the required contract, duplicates ownership, is scaffold-only with no consumer, or prevents the required integration path from passing.

## Local Git policy

Local Git operations may run autonomously inside the local repository and Atlas-owned work area:

- inspect status and diffs;
- initialize local repo when absent;
- create local branch/worktree;
- fetch or pull from remotes;
- create local commits/checkpoints;
- restore Atlas-owned local changes when needed.

External publication requires user approval:

- push to remote;
- create remote branch;
- create PR;
- publish tags;
- merge PR or change protected remote state.

## Package sequence

### Package 0 — Verify current slice

Run and repair the initial tests:

```bash
python -m pytest -q tests/test_twin_forge_git_steward_initial.py
```

Exit criteria:

- focused tests pass;
- no production path is active by accident;
- current status doc records exact command output.

### Package 1 — Instruction Compiler

Implement `agent/twin_control_plane/instruction_compiler.py`.

Required behavior:

- weak local mode gets explicit constrained instructions;
- frontier-assisted mode gets hard constraints plus advisory context and design freedom;
- audit-only mode focuses on review obligations;
- hard constraints are always visible;
- advisory context is clearly labeled;
- stale tests become retirement candidates;
- external publication remains approval-bound.

Required tests:

- weak-local instruction includes refs, gates, tests, proof requirements;
- frontier-assisted instruction supports Twin Challenge but preserves hard constraints;
- audit-only instruction does not imply file mutation authority;
- deterministic output for same input.

### Package 2 — Genesis taxonomy and Greenfield adapter

Implement Project Genesis / Feature Genesis / Module Genesis taxonomy.

Required behavior:

- adapt existing Greenfield sessions into Genesis concepts;
- keep existing Greenfield orchestrator and state machine intact;
- do not create a separate Greenfield pipeline;
- normalize `greenfield_partial` into Feature Genesis semantics where practical.

Required tests:

- empty project maps to Project Genesis;
- existing project new feature maps to Feature Genesis;
- new API/service/UI/test cluster maps to Module Genesis;
- existing Greenfield Safe Apply slice behavior is preserved.

### Package 3 — Integration Impact Gate

Implement `agent/twin_control_plane/integration_impact_gate.py`.

Required behavior:

- compare Existing Project Twin context with Feature Genesis intent;
- identify integration points;
- report contracts to preserve;
- report missing tests and proof requirements;
- use confidence/advisory wording when impact is uncertain.

### Package 4 — BlastMap and Contract Sentinel

Implement:

- `agent/twin_control_plane/blast_map.py`
- `agent/twin_control_plane/contract_sentinel.py`

Required behavior:

- reuse existing Project Twin impact query;
- represent direct/transitive impacts, tests, state/UI/API/persistence hints;
- classify hard/soft/advisory constraints;
- protect Safe Apply, approval, tests, and gates.

### Package 5 — TwinProof and Assumption Breaker

Implement:

- `agent/twin_control_plane/twinproof.py`
- `agent/twin_control_plane/assumption_breaker.py`

Required behavior:

- build Test Inventory from runtime observations and related test refs;
- classify impacted tests, stale candidates, coverage gaps, flaky candidates, redundant candidates;
- mark stale tests as retirement candidates;
- generate Assumption Breaker briefs for no-data, reload, persistence, UI projection, feature flag, and stale contract cases.

### Package 6 — Git Steward concrete adapter

Implement concrete local Git helpers:

- repository detection;
- local repo initialization when absent;
- ignore policy hardening;
- baseline commit;
- Atlas branch/worktree preparation;
- diff collection;
- local commit creation;
- dirty work protection;
- approval-needed result for external publication.

### Package 7 — Patch Impact Gate and Proof Ledger

Implement:

- `agent/twin_control_plane/patch_impact_gate.py`
- `agent/twin_control_plane/proof_ledger.py`

Required behavior:

- compare before/after refs, Git diff, Twin revisions, tests, evidence;
- report accepted, blocked, or needs repair;
- record proof entries linking requirement, plan item, ExecutionPolicy, Git refs, Twin refs, test refs, and evidence refs;
- unavailable verification must remain unavailable.

### Package 8 — Repair Compass

Implement `agent/twin_control_plane/repair_compass.py`.

Required behavior:

- convert gate failures into targeted repair instructions;
- preserve hard constraints;
- prefer local/minimal repair when locality is required;
- keep environment unavailable separate from product regression.

### Package 9 — Forge capability profiles and eval packs

Implement:

- `agent/model_forge/profile_store.py`
- `agent/model_forge/eval_packs.py`
- `agent/model_forge/capability_scoring.py`

Required behavior:

- store model capability profiles with evidence refs;
- update profiles from evaluation outcomes;
- evaluate impact analysis, contract preservation, test generation, stale test judgment, flag reasoning, repair discipline, and evidence discipline;
- feed `ExecutionPolicySelector`.

### Package 10 — Atlas pipeline shadow integration

Wire the pieces into shadow mode first.

Required behavior:

- off mode unchanged;
- shadow mode produces ExecutionPolicy, TwinBrief, Git plan, BlastMap/TwinProof reports where possible;
- shadow artifacts are recorded without taking over execution;
- unavailable shadow reports do not break legacy flow.

### Package 11 — Active integration behind gate

Enable active mode only after shadow evidence.

Required behavior:

- ExecutionPolicy drives instruction compilation;
- Git Steward prepares local branch/worktree where configured;
- Safe Apply remains write boundary;
- post-apply Twin refresh, Patch Impact Gate, TwinProof, Proof Ledger run;
- Repair Compass drives repair loop;
- active mode can be disabled safely.

### Package 12 — Real LLM and real runtime evaluation

Required before `acceptance_complete`.

Required behavior:

- run configured local LLM path if available;
- run stronger/frontier-assisted path if configured, otherwise record unavailable;
- evaluate prompt/instruction behavior with adversarial cases;
- run a representative project or feature through build/test/runtime flow;
- record model id, route, injection level, instruction style, prompt/brief refs, output refs, test output, runtime output, and verdict.

## Adversarial cases

At minimum, include tests/evaluations for:

- unsafe route request for large/critical work;
- hard constraint override attempt;
- missing feature flag baseline;
- stale test incorrectly treated as directly removable;
- unavailable runtime incorrectly reported as passed;
- external publication requested without approval;
- dirty local work before branch/worktree preparation;
- unit tests pass but proof/gate evidence is missing.

## Final acceptance criteria

Do not mark the program complete until all are true:

1. initial tests pass;
2. contract and policy tests pass;
3. integration path tests pass;
4. adversarial tests pass;
5. shadow mode evidence exists;
6. active mode is gated and reversible;
7. real LLM evaluation is recorded or explicitly unavailable;
8. real runtime evaluation is recorded or explicitly unavailable;
9. Proof Ledger explains accepted and blocked outcomes;
10. external publication remains approval-bound;
11. Greenfield is integrated as Genesis;
12. Forge RouteMatrix remains route authority;
13. Project Intelligence remains contextual/advisory;
14. local Git autonomy stays inside local/Atlas-owned boundaries;
15. `docs/atlas_twin_forge_git_steward_current_status.md` has exact evidence.

## Stop conditions

Stop and update current status when:

- a safety invariant would be weakened;
- off mode behavior changes unexpectedly;
- Safe Apply boundary would be bypassed;
- external publication is required but approval is not present;
- required real LLM/runtime evidence is unavailable;
- integration tests reveal a contract conflict.

When stopping, record package, exact failure, files changed, commands run, proposed next fix, and rollback/checkpoint information.

## Suggested PR sequence after this PR

1. Contracts and policy verification.
2. Instruction Compiler.
3. Genesis integration.
4. BlastMap and Contract Sentinel.
5. TwinProof and Assumption Breaker.
6. Git Steward concrete adapter.
7. Patch Impact Gate and Proof Ledger.
8. Repair Compass.
9. Forge profile store and eval packs.
10. Shadow integration.
11. Active integration.
12. Real LLM/runtime evaluation closure.
