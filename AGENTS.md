# KasaneCore Agent Instructions

## Active Goal

The **RV0-RV8 Atlas Project Restore / Visual Contract Recovery** track is closed.

Start here:

```text
docs/atlas_project_restore_visual_recovery_plan.md
```

Then read these completed tracks as context only:

```text
docs/atlas_run_control_cli_banner_plan.md
docs/atlas_server_controlled_ui_cli_plan.md
```

Compatibility entrypoints also point here:

```text
Agent.md
docs/AGENTS.md
```

## Current State

CS9-CS16 completed the backend Run control, Claude-like CLI, and startup banner work. RV0-RV8 then addressed two regressions observed after that work:

1. a newly-created Atlas project can show a PlanPool/run/failure from another project;
2. an HTML Rubik-cube solver task can fail visual verification because the selected visual contract requires canvas evidence.

## Package Status

| # | Goal | Status |
|---|---|---|
| RV0 | Baseline proof and reproduction tests | completed |
| RV1 | Project-scoped client recovery keys | completed |
| RV2 | Bootstrap order and selected-project load | completed |
| RV3 | Backend continuation/recovery workspace isolation audit | completed |
| RV4 | Rubik / cube visual classification fix | completed |
| RV5 | Visual verifier contract evidence and UI diagnostics | completed |
| RV6 | End-to-end project isolation scenario | completed |
| RV7 | Live 8080 Rubik validation | blocked: live 8080 patch generation produced no usable content |
| RV8 | Final review and docs closeout | completed |

## Core Rule

Project restore must be project/workspace-scoped. A global browser hint must never resurrect a PlanPool into a different active project. A new project with no PlanPool must show an empty prompt, not the last global PlanPool.

Visual verification must not require canvas unless the requirement explicitly asks for canvas/WebGL/game-canvas behavior or the artifact intentionally declares and satisfies a canvas contract.

Backend Run control remains the execution authority. Web UI and CLI are clients that send user intent and read backend state/events. They must not own Proposal, Safe Apply, Verification, retry policy, item order, or terminal status.

## Must Preserve

- `unavailable` is not `passed`.
- Mock output is not live evidence.
- UI rendering is not runtime evidence.
- No path may bypass Proposal / Safe Apply / Verification.
- UI and CLI must not directly orchestrate patch generation, patch approval, Safe Apply, verification, or multi-item autopilot execution.
- Backend owns run phase transitions, item order, retry budget, resume behavior, cancellation, and final status.
- Browser reload and CLI process exit must not corrupt a backend run.
- Unknown or stale backend state must never be converted into success.
- Local Only mode must not call external providers.
- Startup banner must not appear in JSON or machine-readable output.
- Project restore must not leak PlanPool, run, progress, or failure state across projects/workspaces.
- Visual contract classification must stay generic and must not add game-only special cases.

## Execution Rules

For any follow-up package derived from this track:

1. Read `docs/atlas_project_restore_visual_recovery_plan.md`.
2. Verify current code before editing.
3. Add or update focused tests before behavior changes where practical.
4. Implement one package at a time.
5. Run focused tests, affected tests, syntax checks, and live 8080 checks when required.
6. Record truthful evidence in `docs/atlas_project_restore_visual_recovery_plan.md`.
7. Advance only when acceptance criteria pass.

## Stop Conditions

Stop for destructive migration, authority conflicts, unavailable live evidence with no truthful blocked state, security-sensitive output issues, direct client-side execution authority reintroduced, cross-project state leakage, or visual verification treating unavailable evidence as passed.

## Completion

This track is complete: RV0-RV6 passed, RV7 truthfully blocked on live 8080 patch generation, and RV8 final review passed according to `docs/atlas_project_restore_visual_recovery_plan.md`.
