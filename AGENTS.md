# KasaneCore Agent Instructions

## Active Goal

The current active track is **CS9-CS16 Atlas Run Control Hardening / Claude-like CLI / Startup Banner**.

Start here:

```text
docs/atlas_run_control_cli_banner_plan.md
```

Then read the completed base plan as context:

```text
docs/atlas_server_controlled_ui_cli_plan.md
```

Supporting context only:

```text
docs/generic_weak_llm_app_hardening_plan.md
docs/weak_llm_large_file_edit_hardening_plan.md
Agent.md
docs/AGENTS.md
```

## Current State

SC0-SC8 moved the normal Web UI execution path to backend `/api/atlas/runs`, added backend run state/events, backend orchestration, a thin CLI wrapper, live 8080 validation, and final evidence review.

CS9-CS16 closes the remaining gaps:

| # | Goal | Status |
|---|---|---|
| CS9 | Run retry/revise backend execution | pending |
| CS10 | Backend-owned item ordering and resume target selection | pending |
| CS11 | Run leases, duplicate-start guard, restart recovery | pending |
| CS12 | Remove or hard-disable legacy UI orchestration | pending |
| CS13 | First-class Claude-like Kasane CLI package | pending |
| CS14 | KasaneCore ASCII startup banner | pending |
| CS15 | Live 8080 validation | pending |
| CS16 | Final evidence review and docs closeout | pending |

Previous base status:

```text
SC0-SC8: done. Treat SC4/SC5/SC6 as MVPs that CS9-CS14 harden.
```

## Core Rule

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

## Execution Rules

For each CS9-CS16 package:

1. Read `docs/atlas_run_control_cli_banner_plan.md`.
2. Verify current code before editing.
3. Add or update focused tests before behavior changes where practical.
4. Implement one package at a time.
5. Run focused tests, affected tests, syntax checks, and live 8080 checks when required.
6. Record truthful evidence in `docs/atlas_run_control_cli_banner_plan.md`.
7. Advance only when acceptance criteria pass.

## Stop Conditions

Stop for destructive migration, authority conflicts, unavailable live evidence with no truthful blocked state, security-sensitive output issues, direct client-side execution authority reintroduced, or banner output leaking into JSON mode.

## Completion

This track is complete only when CS9-CS16 pass or truthfully block according to `docs/atlas_run_control_cli_banner_plan.md`.
