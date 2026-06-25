# KasaneCore Agent Entry Point

This file is a compatibility entrypoint for agents that look for `Agent.md` instead of `AGENTS.md`.

For the authoritative root instructions, read:

```text
AGENTS.md
```

## Current Codex package

For the next Atlas hardening work, start from:

```text
docs/atlas_server_controlled_ui_cli_plan.md
```

Then use the completed weak-LLM / generic hardening work only as supporting context:

```text
docs/generic_weak_llm_app_hardening_plan.md
docs/weak_llm_large_file_edit_hardening_plan.md
```

## Goal

Make Atlas safe when the browser is closed, refreshed, hidden on mobile, or replaced by CLI.

The target split is:

```text
Backend = execution authority, state machine, progress log, recovery source
Web UI  = lightweight viewer plus user-decision sender
CLI     = lightweight viewer plus user-decision sender
```

The UI and CLI must use the same backend `run_id`. Neither client may own the Plan -> Patch -> Apply -> Verify loop.

## Core rule

Browser lifetime must not control Atlas code generation. The backend must own run phase transitions, retry budget, resume skip behavior, cancellation, Proposal / Safe Apply / Verification orchestration, event replay, and terminal status classification.

Preserve all rules in `AGENTS.md`: no bypass around Proposal / Safe Apply / Verification, no remote publication without approval, unavailable is not passed, mock output is not live evidence, and UI rendering is not runtime evidence.
