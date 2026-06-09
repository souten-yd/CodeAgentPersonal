# Atlas Play / Capsule / Portal — Codex / Claude Entrypoint

Use this file as the execution entrypoint after reading root `AGENTS.md`.

## Objective

Implement `PR-PPC-0` through `PR-PPC-12` in the exact order defined by `docs/atlas_play_portal_capsule_implementation_plan.md`. Complete implementation, focused tests, syntax checks, affected tests and the current-status update for every package.

Do not stop after analysis or planning. Do not skip ahead to UI before the contracts, access policy and runtime boundaries are tested.

## Read order

1. `AGENTS.md`
2. `docs/atlas_play_portal_capsule_goal.md`
3. `docs/atlas_play_spec.md`
4. `docs/atlas_capsule_portal_spec.md`
5. `docs/atlas_play_portal_capsule_current_status.md`
6. Only the current package section in `docs/atlas_play_portal_capsule_implementation_plan.md`
7. Current package files, direct dependencies, direct callers and related tests

## Execution loop

For the current package:

1. Confirm the current branch, clean/dirty state and current main baseline.
2. Read the current-status entry and the matching implementation-plan section.
3. Inspect existing code before creating a new service or helper.
4. Add or update contract tests first for security-sensitive behavior.
5. Implement only the current package scope.
6. Run focused tests.
7. Run `python -m py_compile` for changed Python modules.
8. Run `node --check` for changed JavaScript files.
9. Run affected tests and relevant UI/security tests.
10. Update `docs/atlas_play_portal_capsule_current_status.md` with exact evidence.
11. Commit the package as an independently reviewable change.
12. Continue to the next package only after the current package is complete.

## Required implementation behavior

- `/play` is Atlas-only; do not add it to Lumen.
- Capsule, Play and Plan History appear in that order on the right side of the Atlas header.
- Portal is a top-level mode beside Lumen, Atlas, Echo and Nexus.
- Portal Run reuses the public Atlas Play runtime contract.
- Package ZIP, persistent data, session data and temporary data remain separate.
- Portal-generated data supports Save, Snapshot and Discard.
- Package Export never includes Portal runtime data.
- Imported packages remain in quarantine until validation succeeds.
- No general unbounded command endpoint or raw host-filesystem serving.

## Stop conditions

Stop only when one of these is true:

- a destructive or incompatible data migration requires a product decision not covered by the canonical documents;
- a platform limitation prevents a required safety guarantee and no safe fallback exists;
- repository credentials, external infrastructure or an unavailable dependency blocks real verification;
- current code contradicts the goal in a way that cannot be resolved without weakening an existing Atlas safety invariant.

When stopped, record the exact blocker, evidence, completed work and safe next action in the current-status document. Do not mark the package complete.

## Codex start prompt

```text
Read AGENTS.md and docs/atlas_play_portal_capsule_codex_entrypoint.md.
Resume from docs/atlas_play_portal_capsule_current_status.md.
Implement the current PR-PPC work package completely, including tests and status evidence.
Continue package by package in the canonical order until PR-PPC-12 is complete or a documented stop condition is reached.
Preserve all Atlas safety invariants and do not add /play to Lumen.
```

## Claude Code start prompt

```text
Read AGENTS.md and docs/atlas_play_portal_capsule_codex_entrypoint.md as the authoritative instructions.
Resume the current PR-PPC package from the current-status document.
Implement, test, record exact evidence, and continue in order. Do not stop after producing a plan.
```

## Verification of instruction loading

Before implementation, ask the agent to summarize the active repository instructions and name the current PR-PPC package. The answer must identify root `AGENTS.md`, the canonical documents and the current-status file.
