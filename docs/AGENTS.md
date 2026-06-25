# KasaneCore Agent Instructions

This file is an agent-facing entrypoint for implementation tasks under `docs/`.

## Current priority task

Start from:

```text
docs/atlas_run_control_cli_banner_plan.md
```

This is the completed **CS9-CS16 Atlas Run Control Hardening / Claude-like CLI / Startup Banner** track.

Then read the completed base plan as context:

```text
docs/atlas_server_controlled_ui_cli_plan.md
```

Supporting context only:

```text
docs/generic_weak_llm_app_hardening_plan.md
docs/weak_llm_large_file_edit_hardening_plan.md
```

## Core rule

Backend Run control is the execution authority.

```text
Backend = run lifecycle, item order, retry/revise, leases, events, final status
Web UI  = user intent sender and backend status/event viewer
CLI     = Claude-like terminal cockpit over the same backend Run API
```

UI and CLI must not directly orchestrate Plan -> Patch -> Apply -> Verify. They must not directly call patch proposal, patch approval, Safe Apply, Verification, or multi-item autopilot execution endpoints in the normal execution path.

## Package status

Use `docs/atlas_run_control_cli_banner_plan.md` for package sequence and completion evidence:

1. CS9 — Run retry/revise backend execution: completed
2. CS10 — Backend-owned item ordering and resume target selection: completed
3. CS11 — Run leases, duplicate-start guard, restart recovery: completed
4. CS12 — Remove or hard-disable legacy UI orchestration: completed
5. CS13 — First-class Claude-like Kasane CLI package: completed
6. CS14 — KasaneCore ASCII startup banner: completed
7. CS15 — Live 8080 validation: completed
8. CS16 — Final evidence review and docs closeout: completed

## Main files

Start with the package-specific files in `docs/atlas_run_control_cli_banner_plan.md`. Likely central files include:

```text
app/api/atlas_runs.py
agent/atlas_run_schema.py
agent/atlas_run_store.py
agent/atlas_run_events.py
agent/atlas_run_orchestrator.py
web/js/atlas_claude_panel.js
web/js/atlas_pipeline_api.js
scripts/atlas_run_cli.py
tools/run_atlas_server_controlled_flow_eval.py
```

Likely new files:

```text
agent/atlas_run_locks.py
agent/atlas_run_worker.py
agent/atlas_run_recovery.py
agent/atlas_run_retry_policy.py
kasane_cli/__main__.py
kasane_cli/client.py
kasane_cli/commands.py
kasane_cli/repl.py
kasane_cli/render.py
kasane_cli/banner.py
app/startup_banner.py
tools/run_atlas_run_control_hardening_eval.py
```

## Live validation

The user may provide a weak OpenAI-compatible LLM on:

```text
http://127.0.0.1:8080/v1
```

For CS15, run the live checks from `docs/atlas_run_control_cli_banner_plan.md`. If the model is unavailable, record the live check as blocked, not passed.

## Must preserve

- No code path may bypass Proposal / Safe Apply / Verification.
- UI rendering is not runtime evidence.
- Mock output is not live model evidence.
- `unavailable` is not `passed`.
- UI and CLI must not directly own patch/apply/verify orchestration.
- Backend owns item order, retry/revise, cancellation, resume, event replay, and terminal status.
- Unknown or stale run state must not become success.
- JSON/machine-readable CLI output must never include the startup banner.
