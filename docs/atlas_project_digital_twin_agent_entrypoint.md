# Atlas Project Digital Twin Agent Entrypoint

This is the execution entrypoint for Codex or Claude.

## 1. Read order

Read exactly in this order:

1. `AGENTS.md`
2. `docs/atlas_project_digital_twin_goal.md`
3. `docs/atlas_project_digital_twin_current_status.md`
4. the current work package section in `docs/atlas_project_digital_twin_implementation_plan.md`
5. relevant sections of `docs/atlas_project_digital_twin_architecture.md`
6. relevant sections of `docs/atlas_project_digital_twin_contracts.md`
7. target files, direct dependencies, direct callers and related tests

Do not begin with a repository-wide reread after PDT-0.

## 2. Execution behavior

For each work package:

1. verify current status;
2. inventory current implementation facts;
3. identify existing reusable services/schemas/tests;
4. implement the smallest coherent change;
5. run focused tests;
6. run syntax/type checks;
7. run affected tests;
8. fix failures caused by the change;
9. update current status;
10. proceed to the next package only when acceptance criteria pass.

Do not stop at planning unless a truthful blocker exists.

## 3. Stop conditions

Stop and record a blocker only when:

- a safety-sensitive or destructive decision requires user judgment;
- current main contradicts the canonical design so broadly that a local adaptation is unsafe;
- required execution environment is unavailable and no reliable alternative verification exists;
- a schema migration risks data loss without an explicit decision;
- work would require weakening approval, allowed paths, Safe Apply, rollback, retry limits or verification truthfulness.

Implementation size, test duration or context size alone are not blockers.

## 4. Scope discipline

- exactly one PDT work package at a time;
- no unrelated feature work;
- no new parallel memory, skill, graph or context systems;
- reuse current implementations through adapters where possible;
- do not delete legacy paths before parity and migration evidence;
- use symbols, not stale line numbers, to locate code;
- do not redesign UI before backend query value exists.

## 5. Dependency direction

Allowed:

```text
Contracts <- Store/Adapters/Services <- API/UI/Agents
```

Forbidden:

```text
Agent -> SQLite table
UI -> repository implementation
Static parser -> workflow mutation
Skill -> safety authority
Memory -> unverified automatic promotion
```

## 6. Test discipline

Required sequence:

```text
focused tests
-> syntax/type checks
-> affected tests
-> package acceptance scenario
```

Do not claim a test passed unless executed.

When tooling is unavailable:

- record `unavailable`;
- state what was not verified;
- do not convert it to success.

## 7. Safety invariants

Never weaken:

- workflow state and PlanPool authority;
- clarification/critical-event gates;
- profile/envelope/allowed-path rules;
- Safe Apply and revision preconditions;
- rollback and retry bounds;
- command allowlists;
- remote push/direct merge/self-apply restrictions;
- truthful verification;
- project isolation.

The Twin is advisory/contextual. It is not execution authority.

## 8. Token-efficient operation

After PDT-0:

- start from current status;
- read only the current work package;
- read target files and direct relations;
- avoid broad repository scans unless symbols cannot be located;
- reuse existing test fixtures;
- keep final reports to changed files, executed evidence, safety invariants, blockers and next package.

## 9. Current command

Start with:

```text
Implement PDT-0 from the Atlas Project Digital Twin canonical documents.
Do not modify production behavior broadly.
Create the baseline inventory and regression fixtures, update current status,
and continue to PDT-1 only if PDT-0 acceptance criteria are satisfied.
Do not push, merge or self-apply unless explicitly instructed.
```
