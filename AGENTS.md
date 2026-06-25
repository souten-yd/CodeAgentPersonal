# KasaneCore Agent Instructions

## Active Goal

The current active track is **CS0-CS8 Close-Safe Codegen / Server-Controlled UI-CLI**.

Start here:

```text
docs/atlas_server_controlled_ui_cli_plan.md
```

Then read the completed safety base and prior generic weak-LLM work only as supporting context:

```text
docs/generic_weak_llm_app_hardening_plan.md
docs/weak_llm_large_file_edit_hardening_plan.md
```

Compatibility entrypoints also point here:

```text
Agent.md
docs/AGENTS.md
```

## Current State

The weak-LLM large-file edit and generic application hardening base is complete. The next priority is **CS0-CS8**, which makes Atlas safe when the browser is closed, refreshed, hidden on mobile, or replaced by CLI.

```text
CS = Close-Safe Codegen / Client-Safe Control
```

The target architecture is:

```text
Backend = execution authority, state machine, progress log, recovery source
Web UI  = lightweight viewer plus user-decision sender
CLI     = lightweight viewer plus user-decision sender
```

The Web UI and CLI must use the same backend `run_id`. Neither client may own a Plan -> Patch -> Apply -> Verify orchestration loop.

## Core Rule

Browser lifetime must not control Atlas code generation. Atlas must create a backend-owned run, persist progress/events, perform Proposal / Safe Apply / Verification through backend services, and allow UI or CLI to reconnect to the same run later.

Weak models may choose or describe a small edit. Atlas must normalize and dry-run that edit in memory, validators inspect the post-apply file state, deterministic recipes may propose bounded repairs, and Safe Apply remains the only authority that changes files.

Do not add game-only top-level special cases. Games, Web apps, and business/config apps must all use the same generic run, proposal, safe-apply, verification, and event model.

## Package Status

Execute packages in order from `docs/atlas_server_controlled_ui_cli_plan.md`:

| # | Goal | Status |
|---|---|---|
| CS0 | Baseline proof | pending |
| CS1 | Run schema/store/events | pending |
| CS2 | Run API skeleton | pending |
| CS3 | RunOrchestrator MVP | pending |
| CS4 | Multi-item resume/retry/rerun | pending |
| CS5 | CLI thin client | pending |
| CS6 | UI thinning | pending |
| CS7 | Live 8080 weak-LLM validation | pending |
| CS8 | Final LLM evaluation | pending |

## Must Preserve

* `unavailable` is not `passed`.
* Mock output is not live evidence.
* UI rendering is not runtime evidence.
* Inferred graph facts are not verified facts.
* No code path may bypass Proposal / Safe Apply / Verification.
* Web UI and CLI must not directly orchestrate patch generation, patch approval, Safe Apply, verification, or terminal status classification.
* Backend owns run phase transitions, retry budget, resume skip behavior, cancellation, and final status.
* Browser close/reload must not cancel or corrupt an in-progress backend run.
* Weak/standard large existing-file modification remains edit-only.
* Raw full content is forbidden under edit-only unless converted into bounded surgical edits against non-sliced full content.
* Sliced content must never be promoted to full file content.
* Domain-specific repairs must live under registry-style extension points, not scattered top-level branches.
* Project Intelligence and Twin are advisory context/evidence, not execution authority.
* Atlas owns requirement, PlanPool, Proposal, Safe Apply, Verification, Repair, Convergence, and the new backend Run control plane.
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

The current user request authorizes writing the CS0-CS8 planning track to the repository. It does not automatically authorize merging future implementation PRs unless separately requested.

## Execution Rules

For each CS package:

1. Read the active package from `docs/atlas_server_controlled_ui_cli_plan.md`.
2. Verify current implementation against actual code before editing.
3. Reproduce or prove the gap with a failing or missing test where practical.
4. Implement the smallest coherent vertical slice.
5. Preserve all authority boundaries.
6. Run focused tests, affected tests, syntax checks, and available runtime/model evidence.
7. Use `http://127.0.0.1:8080/v1` for LLM-backed live evidence when required.
8. Record unavailable checks truthfully.
9. Update `docs/atlas_server_controlled_ui_cli_plan.md` when a package completes.
10. Advance only when acceptance criteria pass.

## Evidence Rules

Every completed package must record evidence in:

```text
docs/atlas_server_controlled_ui_cli_plan.md
```

Use LLMs for review and comparative evaluation only as advisory evidence. Mechanical tests, deterministic assertions, real provider calls, Safe Apply results, verification results, event replay, recovery drills, Portal runtime behavior, Capsule replay, and rollback drills are authoritative.

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
* focused tests unavailable being marked passed;
* any client-side path reintroduced as execution authority.

## Completion

For the active CS0-CS8 Close-Safe Codegen goal, use:

```text
docs/atlas_server_controlled_ui_cli_plan.md
Agent.md
docs/AGENTS.md
```

The track is complete only when browser lifetime no longer controls code generation: Web UI and CLI both observe/backend-decide the same run, backend events replay after client restart, deterministic tests pass, 8080 live LLM checks pass or truthfully block completion, and final evidence review is written.
