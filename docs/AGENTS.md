# KasaneCore Agent Instructions

This file is an agent-facing entrypoint for implementation tasks under `docs/`.

## Current priority task

Start from:

```text
docs/atlas_server_controlled_ui_cli_plan.md
```

Then use the completed weak-LLM / generic hardening work only as supporting context:

```text
docs/generic_weak_llm_app_hardening_plan.md
docs/weak_llm_large_file_edit_hardening_plan.md
```

## Core rule

Make Atlas safe when the browser is closed, refreshed, hidden on mobile, or replaced by CLI.

```text
Backend = execution authority, state machine, progress log, recovery source
Web UI  = lightweight viewer plus user-decision sender
CLI     = lightweight viewer plus user-decision sender
```

The UI and CLI must use the same backend `run_id`. Neither client may directly orchestrate Plan -> Patch -> Apply -> Verify.

Backend must own:

- run phase transitions;
- retry budget;
- resume skip behavior;
- cancellation;
- Proposal / Safe Apply / Verification orchestration;
- event replay;
- terminal status classification.

Weak models may choose or describe small edits. Atlas must normalize and dry-run them in memory, validators inspect the post-apply state, deterministic recipes may propose bounded repairs, and Safe Apply remains the only authority that changes files.

Do not add game-only special cases at the patch service top level. Games, Web apps, and business/config apps must share the same generic framework.

## Package status

Use `docs/atlas_server_controlled_ui_cli_plan.md` for package sequence and completion evidence:

1. SC0 — Baseline proof: pending
2. SC1 — Run schema/store/events: pending
3. SC2 — Run API skeleton: pending
4. SC3 — RunOrchestrator MVP: pending
5. SC4 — Multi-item resume/retry/rerun: pending
6. SC5 — CLI thin client: pending
7. SC6 — UI thinning: pending
8. SC7 — Live 8080 weak-LLM validation: pending
9. SC8 — Final LLM evaluation: pending

## Main files

Start with the package-specific files in `docs/atlas_server_controlled_ui_cli_plan.md`. Likely central files include:

```text
web/js/atlas_claude_panel.js
web/js/atlas_pipeline_api.js
app/api/atlas_pipeline.py
app/api/atlas_workflow_state.py
app/atlas/workflow_state_contract.py
agent/atlas_journal.py
agent/atlas_pipeline_runner.py
```

Likely new files:

```text
agent/atlas_run_schema.py
agent/atlas_run_store.py
agent/atlas_run_events.py
agent/atlas_run_orchestrator.py
app/api/atlas_runs.py
atlasctl/__main__.py
atlasctl/client.py
atlasctl/render.py
```

## Live validation

The user may provide a weak OpenAI-compatible LLM on:

```text
http://127.0.0.1:8080/v1
```

After implementation, run live checks from `docs/atlas_server_controlled_ui_cli_plan.md`:

- Web app greenfield;
- existing Web app repair;
- business/config scenario;
- CLI starts a run and UI/status API observes it;
- UI/API starts a run and CLI watches it.

If the model is unavailable, record the live check as blocked, not passed.

## Must preserve

- No code path may bypass Proposal / Safe Apply / Verification.
- UI rendering is not runtime evidence.
- Mock output is not live model evidence.
- `unavailable` is not `passed`.
- UI and CLI must not directly own patch/apply/verify orchestration.
- Weak/standard large existing-file modification remains edit-only.
- Raw full content is forbidden under edit-only unless converted into bounded surgical edits against non-sliced full content.
- Sliced content must never become full file content.
- Domain-specific repairs must live under registry-style extension points.
