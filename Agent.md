# KasaneCore Agent Entry Point

This file is the compatibility entrypoint for agents that look for `Agent.md`.

For the authoritative root instructions, read:

```text
AGENTS.md
```

## Current package

Start from:

```text
docs/atlas_project_restore_visual_recovery_plan.md
```

This is the **RV0-RV8 Atlas Project Restore / Visual Contract Recovery** track.

Then read these completed tracks as context only:

```text
docs/atlas_run_control_cli_banner_plan.md
docs/atlas_server_controlled_ui_cli_plan.md
```

## Goal

Recover two user-visible regressions:

1. a newly-created Atlas project can re-render a PlanPool/run/failure from another project;
2. an HTML Rubik-cube solver task can fail visual verification because the selected visual contract incorrectly requires canvas evidence.

## Package order

1. RV0 — Baseline proof and reproduction tests
2. RV1 — Project-scoped client recovery keys
3. RV2 — Bootstrap order and selected-project load
4. RV3 — Backend continuation/recovery workspace isolation audit
5. RV4 — Rubik / cube visual classification fix
6. RV5 — Visual verifier contract evidence and UI diagnostics
7. RV6 — End-to-end project isolation scenario
8. RV7 — Live 8080 Rubik validation
9. RV8 — Final review and docs closeout

## Core rule

Project restore must be project/workspace-scoped. A global browser hint must never resurrect a PlanPool into a different active project. A new project with no PlanPool must show an empty prompt, not the last global PlanPool.

Visual verification must not require canvas unless the requirement explicitly asks for canvas/WebGL/game-canvas behavior or the artifact intentionally declares and satisfies a canvas contract.

Preserve all rules in `AGENTS.md`: no bypass around Proposal / Safe Apply / Verification, unavailable is not passed, mock output is not live evidence, UI rendering is not runtime evidence, Backend Run control remains authoritative, and UI/CLI must not directly own patch/apply/verify orchestration.
