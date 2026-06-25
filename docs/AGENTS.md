# KasaneCore Agent Instructions

This file is an agent-facing entrypoint for implementation tasks under `docs/`.

## Current priority task

Start from:

```text
docs/atlas_project_restore_visual_recovery_plan.md
```

This is the **RV0-RV8 Atlas Project Restore / Visual Contract Recovery** track.

Then read completed tracks as context only:

```text
docs/atlas_run_control_cli_banner_plan.md
docs/atlas_server_controlled_ui_cli_plan.md
```

## Core rule

Project restore must be project/workspace-scoped:

```text
Project A pool/run/failure must never render in Project B.
New project with no pool must show an empty prompt.
Global localStorage hints must not override active project identity.
```

Visual verification must be requirement-scoped:

```text
Rubik HTML solver = interactive web app or UI component by default.
Canvas is required only when canvas/WebGL/game-canvas is explicit or intentionally declared.
```

Backend Run control remains authoritative. UI and CLI send user intent and read backend state/events. They must not directly orchestrate Plan -> Patch -> Apply -> Verify.

## Package status

Use `docs/atlas_project_restore_visual_recovery_plan.md` for package sequence and completion evidence:

1. RV0 — Baseline proof and reproduction tests: pending
2. RV1 — Project-scoped client recovery keys: pending
3. RV2 — Bootstrap order and selected-project load: pending
4. RV3 — Backend continuation/recovery workspace isolation audit: pending
5. RV4 — Rubik / cube visual classification fix: pending
6. RV5 — Visual verifier contract evidence and UI diagnostics: pending
7. RV6 — End-to-end project isolation scenario: pending
8. RV7 — Live 8080 Rubik validation: pending
9. RV8 — Final review and docs closeout: pending

## Main files

Start with the package-specific files in `docs/atlas_project_restore_visual_recovery_plan.md`. Likely central files include:

```text
web/js/atlas_claude_panel.js
web/js/app.js
web/js/atlas_pipeline_api.js
app/api/atlas_pipeline.py
agent/atlas_continuation_service.py
agent/atlas_recovery_service.py
agent/atlas_journal.py
agent/atlas_auto_verification_service.py
agent/atlas_visual_requirement_normalizer.py
agent/atlas_visual_task_classifier.py
agent/atlas_visual_contract_registry.py
agent/atlas_visual_artifact_verifier.py
agent/atlas_playwright_smoke_verifier.py
```

Likely new/updated tests:

```text
tests/test_atlas_project_restore_isolation.py
tests/test_atlas_project_picker_bootstrap_contract.py
tests/test_atlas_continuation_workspace_isolation.py
tests/test_atlas_visual_rubik_contract.py
tests/test_atlas_visual_failure_diagnostics.py
tests/test_atlas_project_restore_e2e_contract.py
tests/test_atlas_restore_visual_recovery_eval.py
```

## Live validation

The user may provide a weak OpenAI-compatible LLM on:

```text
http://127.0.0.1:8080/v1
```

For RV7, run the live Rubik/project-isolation checks from `docs/atlas_project_restore_visual_recovery_plan.md`. If the model is unavailable, record the live check as blocked, not passed.

## Must preserve

- No code path may bypass Proposal / Safe Apply / Verification.
- UI rendering is not runtime evidence.
- Mock output is not live model evidence.
- `unavailable` is not `passed`.
- UI and CLI must not directly own patch/apply/verify orchestration.
- Backend owns item order, retry/revise, cancellation, resume, event replay, and terminal status.
- Unknown or stale run state must not become success.
- Project restore must not leak PlanPool/run/progress/failure state across workspaces.
- Visual verification must not require canvas for DOM/CSS/SVG HTML apps unless explicit.
