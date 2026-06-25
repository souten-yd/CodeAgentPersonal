# KasaneCore Agent Entry Point

This file is a compatibility entrypoint for agents that look for `Agent.md` instead of `AGENTS.md`.

For the authoritative root instructions, read:

```text
AGENTS.md
```

## Current package

For the next Atlas hardening work, start from:

```text
docs/atlas_run_control_cli_banner_plan.md
```

This is the **CS9-CS16 Atlas Run Control Hardening / Claude-like CLI / Startup Banner** track.

Then read the completed base plan as context:

```text
docs/atlas_server_controlled_ui_cli_plan.md
```

## Goal

Close the remaining backend Run control gaps, make the CLI feel like a Claude-style terminal cockpit, and add a safe KasaneCore ASCII startup banner.

## Package order

1. CS9 — Run retry/revise backend execution
2. CS10 — Backend-owned item ordering and resume target selection
3. CS11 — Run leases, duplicate-start guard, restart recovery
4. CS12 — Remove or hard-disable legacy UI orchestration
5. CS13 — First-class Claude-like Kasane CLI package
6. CS14 — KasaneCore ASCII startup banner
7. CS15 — Live 8080 validation
8. CS16 — Final evidence review and docs closeout

## Core rule

Backend Run control is the execution authority. Web UI and CLI send user intent and read backend state/events. They must not own Proposal, Safe Apply, Verification, retry policy, item order, or terminal status.

Preserve all rules in `AGENTS.md`: no bypass around Proposal / Safe Apply / Verification, unavailable is not passed, mock output is not live evidence, UI rendering is not runtime evidence, and banner output must not appear in JSON mode.
