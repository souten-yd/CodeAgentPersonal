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
  -> Interface First / Schema Guardian / StateMirror hints when applicable
  -> model-specific instruction
  -> LLM output
  -> Proposal / Safe Apply
  -> local commit
  -> Twin refresh
  -> Patch Impact Gate
  -> TwinProof
  -> StateMirror / Schema Guardian checks
  -> Proof Ledger
  -> Anti-Pattern Memory update
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
- external publication remains approval-bound;
- `interface_first` style emits concrete interface/schema/state/test-contract steps before implementation steps.

Required tests:

- weak-local instruction includes refs, gates, tests, proof requirements;
- frontier-assisted instruction supports Twin Challenge but preserves hard constraints;
- audit-only instruction does not imply file mutation authority;
- deterministic output for same input;
- `interface_first` instruction includes public interfaces, persistence/schema expectations, and required tests before code-edit instructions.

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

### Package 2A — No-Data Bootstrap Gate and Interface First Generator

Implement the no-data and interface-first controls required for empty or partially-known projects.

Suggested files:

- `agent/twin_control_plane/no_data_bootstrap_gate.py`
- `agent/twin_control_plane/interface_first_generator.py`

Required behavior:

- treat empty stores, missing persisted state, no prior runtime evidence, and no prior tests as normal cases;
- require bootstrap acceptance scenarios before implementation is accepted;
- emit interface skeletons for APIs, service boundaries, artifact schemas, UI projection contracts, persistence schemas, and test fixture contracts;
- integrate with Project/Feature/Module Genesis so new work starts from interfaces and proof requirements, not freeform code;
- feed Instruction Compiler so weak models receive concrete skeletons and frontier-assisted models receive design constraints plus proof obligations.

Required tests:

- empty project creates bootstrap requirements rather than assuming initial data exists;
- feature with new persistence requires create/read/reload proof;
- new UI projection requires backend-state-to-UI-state proof;
- generated instruction includes interface/schema/test-contract sections before implementation sections.

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
- protect Safe Apply, approval, tests, and gates;
- delegate schema compatibility findings to Schema Guardian when available;
- delegate state/UI/persistence consistency findings to StateMirror when available.

### Package 4A — Schema Guardian

Implement `agent/twin_control_plane/schema_guardian.py`.

Required behavior:

- track API response schemas, artifact schemas, persisted JSON/SQLite/data-file shapes, event payloads, and UI projection contracts;
- compare before/after schema snapshots using Git diff and Twin context where possible;
- classify changes as compatible, migration-required, breaking, or unknown;
- require migration notes and tests for migration-required or breaking changes;
- never mark a schema-affecting patch accepted from unit tests alone.

Required tests:

- compatible additive schema change is allowed with proof;
- breaking response schema change requires explicit migration/proof;
- artifact schema drift is reported even when unit tests pass;
- unknown schema confidence remains advisory but visible.

### Package 4B — StateMirror

Implement `agent/twin_control_plane/state_mirror.py`.

Required behavior:

- compare backend workflow state, UI projection state, persisted state, and runtime observations;
- detect UI controls that disagree with backend authority;
- detect reload/persistence regressions;
- report state gaps as proof requirements for TwinProof and Patch Impact Gate;
- support Atlas-specific state paths such as workflow_state, can_execute/can_continue, plan revision, proposal status, and Portal run/capsule state.

Required tests:

- backend cannot execute but UI exposes execute is flagged;
- reload loses completed plan item count is flagged;
- persisted artifact state differs from runtime state is flagged;
- unavailable runtime evidence is not treated as pass.

### Package 5 — TwinProof and Assumption Breaker

Implement:

- `agent/twin_control_plane/twinproof.py`
- `agent/twin_control_plane/assumption_breaker.py`

Required behavior:

- build Test Inventory from runtime observations and related test refs;
- classify impacted tests, stale candidates, coverage gaps, flaky candidates, redundant candidates;
- mark stale tests as retirement candidates;
- generate Assumption Breaker briefs for no-data, reload, persistence, UI projection, feature flag, and stale contract cases;
- consume No-Data Bootstrap Gate, StateMirror, and Schema Guardian findings when present.

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
- record proof entries linking requirement, plan item, ExecutionPolicy, Git refs, Twin refs, test refs, gate findings, and evidence refs;
- unavailable verification must remain unavailable;
- consume Schema Guardian, StateMirror, TwinProof, and BlastMap findings before acceptance.

### Package 8 — Repair Compass

Implement `agent/twin_control_plane/repair_compass.py`.

Required behavior:

- convert gate failures into targeted repair instructions;
- preserve hard constraints;
- prefer local/minimal repair when locality is required;
- keep environment unavailable separate from product regression;
- include anti-pattern hints from Anti-Pattern Memory when available.

### Package 8A — Anti-Pattern Memory

Implement `agent/twin_control_plane/anti_pattern_memory.py`.

Required behavior:

- record recurring failure patterns from Proof Ledger, runtime incidents, rejected patches, and Repair Compass outcomes;
- produce short guardrail hints for future TwinBrief and Instruction Compiler prompts;
- never treat a past failure pattern as absolute truth without confidence and evidence refs;
- support model-specific weaknesses, route-specific mistakes, and project-specific invariants.

Required tests:

- repeated test weakening attempts become a future hard/soft guardrail hint;
- environment issue is not memorized as product-regression truth;
- memory entry round-trips with evidence refs and confidence.

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

### Package 9A — Golden Patch Retrieval and Skill Distiller

Implement retrieval/distillation as evidence-backed optional accelerators, not as acceptance gates for P0.

Suggested files:

- `agent/model_forge/golden_patch_retrieval.py`
- `agent/model_forge/skill_distiller.py`

Required behavior:

- retrieve prior successful patches by task category, route, model, affected refs, gate findings, and proof outcome;
- use retrieved patches as advisory examples only;
- distill recurring successful patterns into compact skills with evidence refs;
- never override current Project Twin, Contract Sentinel, StateMirror, Schema Guardian, or TwinProof findings;
- allow disabling retrieval/distillation without changing correctness.

Required tests:

- matching successful patch is returned as advisory context;
- unrelated patch is not returned above confidence threshold;
- distilled skill includes evidence refs and scope;
- disabling retrieval leaves ExecutionPolicy correctness unchanged.

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
- unit tests pass but proof/gate evidence is missing;
- schema drift passes unit tests but lacks migration/proof;
- UI projection state disagrees with backend authority;
- no-data project assumes preexisting state;
- retrieved golden patch conflicts with current Twin/Contract findings.

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
15. No-Data Bootstrap Gate covers empty/unknown project states;
16. Interface First Generator emits interface/schema/test contracts before implementation;
17. StateMirror checks backend/UI/persistence/runtime consistency;
18. Schema Guardian checks API/artifact/persistence/event schema compatibility;
19. Anti-Pattern Memory, Golden Patch Retrieval, and Skill Distiller are either implemented as advisory/evidence-backed features or explicitly deferred with no P0 correctness dependency;
20. `docs/atlas_twin_forge_git_steward_current_status.md` has exact evidence.

## Stop conditions

Stop and update current status when:

- a safety invariant would be weakened;
- off mode behavior changes unexpectedly;
- Safe Apply boundary would be bypassed;
- external publication is required but approval is not present;
- required real LLM/runtime evidence is unavailable;
- integration tests reveal a contract conflict;
- schema/state/no-data findings cannot be represented in the current contracts;
- retrieved examples or distilled skills would override current evidence.

When stopping, record package, exact failure, files changed, commands run, proposed next fix, and rollback/checkpoint information.

## Suggested PR sequence after this PR

1. Contracts and policy verification.
2. Instruction Compiler and Interface First Generator.
3. Genesis integration and No-Data Bootstrap Gate.
4. Integration Impact Gate.
5. BlastMap, Contract Sentinel, Schema Guardian, and StateMirror.
6. TwinProof and Assumption Breaker.
7. Git Steward concrete adapter.
8. Patch Impact Gate and Proof Ledger.
9. Repair Compass and Anti-Pattern Memory.
10. Forge profile store and eval packs.
11. Golden Patch Retrieval and Skill Distiller.
12. Shadow integration.
13. Active integration.
14. Real LLM/runtime evaluation closure.
