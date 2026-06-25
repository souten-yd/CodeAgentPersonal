# KasaneCore Agent Instructions

## Active Goal

The current active track is **Generic Weak LLM App Hardening**.

Start here:

```text
docs/generic_weak_llm_app_hardening_plan.md
```

Then read the completed safety base:

```text
docs/weak_llm_large_file_edit_hardening_plan.md
```

Compatibility entrypoints also point here:

```text
Agent.md
docs/AGENTS.md
```

## Current State

The weak-LLM large-file edit safety base is complete. The generic continuation has now completed GA1-GA8:

- post-apply preview for generic validation;
- sliced-content salvage hardening;
- generic contract registry;
- repair recipe registry;
- file-type-aware edit policy and primitives;
- generic post-apply validators;
- live 8080 weak-model checks for Web and business/config scenarios;
- documentation and agent workflow entrypoint alignment.

## Core Rule

Weak models may choose or describe a small edit. Atlas must normalize and dry-run that edit in memory, validators inspect the post-apply file state, deterministic recipes may propose bounded repairs, and Safe Apply remains the only authority that changes files.

Do not add new game-only top-level special cases. WebGL/Canvas repair is one domain recipe under the generic repair/contract framework.

## Package Status

Execute packages in order, one coherent PR per item unless the user explicitly requests direct write-only changes:

| # | Branch | Goal | Status |
|---|---|---|---|
| GA1 | `codex/generic-post-apply-preview` | Post-Apply Preview for generic validation | done |
| GA2 | `codex/harden-sliced-content-salvage` | Harden sliced-content salvage | done |
| GA3 | `codex/generic-contract-registry` | Generic Contract Registry | done |
| GA4 | `codex/repair-recipe-registry` | Repair Recipe Registry | done |
| GA5 | `codex/filetype-edit-primitives` | File-type-aware edit policy and primitives | done |
| GA6 | `codex/generic-preview-validators` | Generic validators after preview | done |
| GA7 | `codex/generic-weak-llm-live-checks` | 8080 weak-model generic live checks | done |
| GA8 | `codex/generic-agent-docs-update` | Documentation and agent workflow update | done |

## Must Preserve

* `unavailable` is not `passed`.
* Mock output is not live evidence.
* UI rendering is not runtime evidence.
* Inferred graph facts are not verified facts.
* No code path may bypass Proposal / Safe Apply / Verification.
* Weak/standard large existing-file modification remains edit-only.
* Raw full content is forbidden under edit-only unless converted into bounded surgical edits against non-sliced full content.
* Sliced content must never be promoted to full file content.
* Domain-specific repairs must live under registry-style extension points, not scattered top-level branches.
* Project Intelligence and Twin are advisory context/evidence, not execution authority.
* Atlas owns requirement, PlanPool, Proposal, Safe Apply, Verification, Repair, and Convergence.
* Portal owns runtime execution, artifact lifecycle, generated-data save/discard, and Capsule replay.
* Forge owns model/provider/profile routing and benchmark evidence.
* Nexus owns external web research. External/web calls remain policy-gated and disabled by default.
* No external provider may run in Local Only mode.
* Secrets must never be persisted, logged, returned by API, embedded in Capsule ZIPs, or included in Project Intelligence stores.
* Capsule package ZIPs must remain immutable and data-free by default.

## Local Git Policy

Local Git operations are allowed inside the local repository and Atlas-owned work area:

* status/diff/log inspection;
* local branch/worktree creation;
* local commits/checkpoints;
* fetch/pull/clone from remotes;
* restoring Atlas-owned local changes.

Remote publication or protected remote changes require explicit user authorization:

* push;
* PR creation;
* remote branch/tag publication;
* PR merge;
* protected remote state changes.

The current user request authorizes the GA package workflow: one item per PR, with PR creation and merge after each package passes validation.

## Execution Rules

For each package:

1. Read the active package from `docs/generic_weak_llm_app_hardening_plan.md`.
2. Verify the current implementation against actual code before editing.
3. Reproduce or prove the gap with a failing or missing test where practical.
4. Implement the smallest coherent vertical slice.
5. Preserve all authority boundaries.
6. Run focused tests, affected tests, syntax checks, and available runtime/model evidence.
7. Use `http://127.0.0.1:8080/v1` for LLM-backed code or live evidence when required.
8. Record unavailable checks truthfully.
9. Update `docs/generic_weak_llm_app_hardening_plan.md` when a package completes.
10. Advance only when acceptance criteria pass.

## Evidence Rules

Every completed package must record the evidence template in:

```text
docs/generic_weak_llm_app_hardening_plan.md
```

Use LLMs for review and comparative evaluation only as advisory evidence. Mechanical tests, deterministic graph assertions, real provider calls, Portal runtime behavior, Capsule replay, and rollback drills are authoritative.

## Stop Conditions

Stop only for:

* destructive migration requiring explicit approval;
* changing default external-code exposure;
* deleting legacy model execution paths;
* safety or authority conflict with Proposal / Safe Apply / Verification;
* required live model/runtime/web evidence unavailable with no truthful alternative;
* security issue involving credentials, external providers, package import, runtime execution, or generated artifacts;
* readiness unavailable being treated as trusted;
* non-unique anchor being accepted for slot assist;
* direct repository workspace apply during evaluation;
* focused tests unavailable being marked passed.

## Completion

For the active Generic Weak LLM App Hardening goal, use:

```text
docs/generic_weak_llm_app_hardening_plan.md
docs/weak_llm_large_file_edit_hardening_plan.md
Agent.md
docs/AGENTS.md
```

The Generic Weak LLM App Hardening package sequence is complete once GA8 is merged.
