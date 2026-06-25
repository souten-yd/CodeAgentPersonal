# Atlas CS9-CS16 Run Control, Claude-like CLI, and Startup Banner Plan

> Active follow-up track after SC0-SC8 / CS0-CS8.
>
> Goal: close the remaining backend-run control gaps, make the CLI feel like a Claude Code-style cockpit, and show a KasaneCore ASCII banner at startup.

## Why this plan exists

SC0-SC8 moved the normal Web UI approval path to `/api/atlas/runs` and added backend run state/events, a backend orchestrator, a thin CLI wrapper, live 8080 validation, and final evidence review.

The remaining gaps are still important:

1. `/api/atlas/runs/{run_id}/retry` and `/revise` currently record deferred events instead of executing backend retry/revision.
2. Web UI still derives and sends `item_ids`; backend should own item order, skip logic, and resume targets.
3. Backend runs use FastAPI background tasks but do not have run leases, duplicate-start protection, or server-restart recovery.
4. Legacy browser orchestration remains in `approveAndRunPipelineLegacyDisabled()` and can accidentally be revived.
5. CLI exists as `scripts/atlas_run_cli.py`, but not yet as a first-class Claude-like interactive interface.
6. KasaneCore has no startup identity/banner in CLI/server startup.

This track fixes those without weakening Proposal, Safe Apply, Verification, approvals, safety gates, or local-only provider policy.

## Naming

Use **CS9-CS16** for this follow-up track.

```text
CS = Close-Safe Codegen / Client-Safe Control
```

Earlier completed packages may still be named `SC0-SC8` in main. Do not rename historic evidence unless the package explicitly updates docs. From this plan forward, use **CS9-CS16**.

## Final target

```text
Backend Run Control Plane
  owns run lifecycle, item ordering, retry/revise, leases, resume, terminal status

Web UI
  sends user intent only; watches backend status/events; cannot execute patch/apply/verify directly

Kasane CLI
  Claude-like terminal cockpit: natural-language prompt + slash commands + streaming run events

Startup Identity
  KasaneCore ASCII banner appears at CLI/server startup without breaking logs, JSON mode, or tests
```

## Non-negotiable rules

- No code path may bypass Proposal, Safe Apply, or Verification.
- `unavailable` is never `passed`.
- Mock output is not live model evidence.
- UI rendering is not runtime evidence.
- Project Intelligence / Twin are advisory, not execution authority.
- Local-only mode must not call external providers.
- Secrets must not be persisted, logged, printed in CLI transcripts, included in Capsule ZIPs, or included in evidence bundles.
- Remote publication still requires explicit user authorization.
- UI and CLI must not call patch proposal, patch approval, Safe Apply, Verification, or multi-item autopilot execution endpoints directly.
- Backend owns item order, retry budget, resume skip logic, cancellation, terminal status, and evidence status.
- The legacy UI orchestration path must not be callable from any visible UI button or normal code path.

## Current implementation snapshot to verify first

Before editing, inspect these files and confirm the current state:

```text
AGENTS.md
Agent.md
docs/AGENTS.md
docs/atlas_server_controlled_ui_cli_plan.md
app/api/atlas_runs.py
agent/atlas_run_schema.py
agent/atlas_run_store.py
agent/atlas_run_events.py
agent/atlas_run_orchestrator.py
web/js/atlas_claude_panel.js
web/js/atlas_pipeline_api.js
scripts/atlas_run_cli.py
tools/run_atlas_server_controlled_flow_eval.py
tests/test_atlas_run_api.py
tests/test_atlas_run_orchestrator.py
tests/test_atlas_run_cli.py
tests/test_atlas_runtime_status_panel_contract.py
tests/test_atlas_server_controlled_flow_eval.py
```

Expected current gaps:

- `retry_run()` and `revise_run()` in `app/api/atlas_runs.py` call a deferred-control helper rather than starting backend execution.
- `approveAndRunPipeline()` in `web/js/atlas_claude_panel.js` fetches PlanPool items and sends `item_ids` to `/api/atlas/runs`.
- `approveAndRunPipelineLegacyDisabled()` still contains direct `generatePatchProposal`, `decidePatchProposal`, and `runMultiItemAutopilot` calls.
- `scripts/atlas_run_cli.py` is a useful thin wrapper but not a first-class interactive CLI package.
- There is no shared startup banner module.

If the code no longer matches these assumptions, update this plan before implementing.

## Target file layout

Prefer these files for new work:

```text
agent/atlas_run_locks.py
agent/atlas_run_worker.py
agent/atlas_run_recovery.py
agent/atlas_run_retry_policy.py
app/api/atlas_runs.py
agent/atlas_run_orchestrator.py
agent/atlas_run_schema.py
agent/atlas_run_store.py
web/js/atlas_claude_panel.js
web/js/atlas_pipeline_api.js
kasane_cli/__init__.py
kasane_cli/__main__.py
kasane_cli/client.py
kasane_cli/commands.py
kasane_cli/repl.py
kasane_cli/render.py
kasane_cli/banner.py
scripts/atlas_run_cli.py
app/startup_banner.py
main.py
app/server.py
tools/run_atlas_run_control_hardening_eval.py
```

Keep `scripts/atlas_run_cli.py` as a compatibility wrapper that delegates to `kasane_cli` after the new package lands.

## Claude-like CLI target

The CLI should feel like a compact local Claude Code-style cockpit, not a raw REST wrapper.

### Launch commands

Support these entrypoints:

```text
python -m kasane_cli
python -m kasane_cli --project .
python -m kasane_cli --base-url http://127.0.0.1:8000
python scripts/atlas_run_cli.py interactive
```

Optional packaging entrypoint, if project packaging supports it later:

```text
kasane
```

### Startup output

Interactive mode prints:

```text
<ASCII KasaneCore banner>
KasaneCore Atlas CLI
project: <detected project path>
server:  http://127.0.0.1:8000
model:   <from /api/system/status or /v1/models when available; unavailable is shown as unavailable>

Type /help for commands. Type natural language to create or continue an Atlas plan.
```

Do not print the banner in `--json`, `--quiet`, or non-interactive machine-readable command output.

### Prompt style

Use a simple prompt:

```text
kasane> 
```

or, when a run is active:

```text
kasane[atlas_run_xxx]> 
```

### Slash commands

Implement at least:

```text
/help
/status
/project [path]
/model
/plan <goal>
/pools
/pool <pool_id>
/run <pool_id>
/watch [run_id]
/events [run_id] [--after N]
/approve [run_id]
/decision <run_id> <decision>
/retry [run_id]
/revise [run_id] <note>
/cancel [run_id]
/diff [run_id]
/open
/clear
/exit
```

Natural language input without a slash should behave like:

1. If no active pool: create a PlanPool from the text.
2. If a pool is ready and not running: ask for confirmation or use `/run`.
3. If a run is active: treat text as a note/decision only if the run requires user action; otherwise show `/help` hint.

### CLI contract

- CLI must call PlanPool APIs for planning/list/show.
- CLI must call `/api/atlas/runs/*` for execution/status/events/decision/retry/revise/cancel.
- CLI must not call direct patch proposal, patch approval, Safe Apply, Verification, or multi-item autopilot endpoints.
- CLI must support event watching after process restart with `--after` cursor.
- CLI must redact secret-looking values in rendered output.
- CLI must have `--json` mode for scripts and tests.
- Interactive display can be pretty, but tests must verify the underlying JSON commands.

## ASCII banner target

Add a shared banner provider, for example:

```text
kasane_cli/banner.py
app/startup_banner.py
```

Suggested default banner:

```text
 _  __                         ____               
| |/ /__ _ ___  __ _ _ __   ___/ ___|___  _ __ ___ 
| ' // _` / __|/ _` | '_ \ / _ \ |   / _ \| '__/ _ \
| . \ (_| \__ \ (_| | | | |  __/ |__| (_) | | |  __/
|_|\_\__,_|___/\__,_|_| |_|\___|\____\___/|_|  \___|

        Atlas • Portal • Forge • Twin
```

Rules:

- Keep the banner plain ASCII only.
- No external font files.
- No ANSI color by default; optional color only when TTY and not `NO_COLOR`.
- Do not print banner in JSON mode, test mode, or when `KASANE_NO_BANNER=1`.
- Server startup banner must not break structured logs or uvicorn startup.
- CLI banner must be covered by snapshot/string tests.

## Work packages

### CS9: Run retry/revise backend execution

Goal: make `/retry` and `/revise` real backend control-plane operations instead of deferred event stubs.

Implementation tasks:

1. Add `agent/atlas_run_retry_policy.py`.
2. Extend `AtlasRunState.metadata` or schema fields for:
   - `retry_count`
   - `max_retries`
   - `last_retry_reason`
   - `revision_requested_at`
   - `revision_note`
3. Update `/api/atlas/runs/{run_id}/retry` to:
   - reject non-existing run;
   - reject or no-op terminal completed run unless `mode=rerun` is explicit;
   - increment retry count with a hard cap;
   - start backend `resume` execution for failed/blocked/incomplete items;
   - emit `run_retry_requested`, `run_retry_started`, and terminal events.
4. Update `/api/atlas/runs/{run_id}/revise` to one of two explicit modes:
   - **plan revision request mode**: attach revision note and call existing PlanPool revision API if safe and available;
   - **blocked decision mode**: record `requires_user_action=true`, `next_actions=["revise_plan"]`, and do not claim execution started.
5. Add clear response fields:
   - `execution_started`
   - `deferred`
   - `reason`
   - `next_actions`
6. UI retry button must call Run API retry when a run_id is known; fall back to new run resume only if run_id is absent.
7. CLI `/retry` and `/revise` must use the real endpoints.

Acceptance:

- Retry of a failed first item starts backend execution and does not call browser patch/apply endpoints.
- Retry budget is enforced.
- Completed run retry is rejected unless explicit rerun.
- Revise does not falsely mark execution as started when only a revision note was recorded.
- Tests prove `/retry` no longer returns only `deferred=True` for retryable runs.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_run_retry_revise.py
python -m pytest -q tests/test_atlas_run_api.py tests/test_atlas_run_orchestrator.py
```

### CS10: Backend-owned item ordering and resume target selection

Goal: UI/CLI send user intent only; backend derives runnable item order from PlanPool and run state.

Implementation tasks:

1. Add `select_run_items(pool, state, mode, requested_item_id="")` helper in `agent/atlas_run_orchestrator.py` or a new `agent/atlas_run_selection.py`.
2. In `/api/atlas/runs`, allow clients to omit `item_ids`.
3. Change Web UI `approveAndRunPipeline()` to stop fetching PlanPool just to build `item_ids`.
4. Change CLI `start` / `/run` default to omit `item_ids`; keep explicit `--item-id` for advanced/manual cases.
5. Backend selection rules:
   - fresh: all runnable plan items in PlanPool order;
   - resume: all runnable items not already completed in run state or PlanPool completion metadata;
   - rerun: all runnable items after resetting execution state;
   - explicit item: only that item if runnable and allowed.
6. Add backend events recording selected item order.

Acceptance:

- UI createRun payload contains no `item_ids` in normal approval path.
- Backend event `run_items_selected` records item order.
- Resume skips completed items without UI-provided item IDs.
- Two items editing the same file still run one-at-a-time against current workspace.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_run_item_selection.py
python -m pytest -q tests/test_atlas_runtime_status_panel_contract.py
```

### CS11: Run leases, duplicate-start guard, and restart recovery

Goal: make backend runs robust against double starts and server/process interruptions.

Implementation tasks:

1. Add `agent/atlas_run_locks.py` with per-run lock files or process-local locks plus durable lease metadata.
2. Add fields/metadata:
   - `lease_owner`
   - `lease_acquired_at`
   - `lease_expires_at`
   - `worker_heartbeat_at`
   - `resume_after_restart_supported`
3. `start_run` and `create_run(auto_start=True)` must reject or idempotently return if run is already active.
4. Long phases must update heartbeat events/state.
5. Add `agent/atlas_run_recovery.py` to scan queued/running stale runs on startup or via admin endpoint.
6. Initial recovery can mark stale running runs as `blocked` with `next_actions=["retry", "inspect_events"]`; full automatic resume can be later if unsafe.
7. Add optional endpoint:

```text
POST /api/atlas/runs/recover-stale
```

Acceptance:

- Double start does not create two concurrent orchestrators.
- Stale running run is detected truthfully.
- Recovery never marks unknown state as success.
- Browser close remains safe; server restart becomes at least inspectable/retryable.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_run_lease_recovery.py
```

### CS12: Remove or hard-disable legacy UI orchestration

Goal: ensure direct browser orchestration cannot return accidentally.

Implementation tasks:

1. Delete `approveAndRunPipelineLegacyDisabled()` if no tests require it.
2. If deletion is too risky, move it to a separate file under `web/js/legacy/` not loaded by default.
3. Add a test that the loaded `web/js/atlas_claude_panel.js` normal bundle does not contain direct approval-path calls to:
   - `generatePatchProposal(`
   - `decidePatchProposal(`
   - `runMultiItemAutopilot(`
   inside any callable approval function.
4. Ensure visible buttons call only the backend Run API path.
5. Keep direct APIs in `atlas_pipeline_api.js` only for compatibility/manual tools, not approval execution.

Acceptance:

- No loaded UI function named like `approveAndRunPipeline*` directly calls patch/apply/verify/autopilot endpoints.
- Existing UI tests pass.
- Legacy direct orchestration cannot be invoked by typo, global exposure, or visible button.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_ui_no_legacy_orchestration.py
python -m pytest -q tests/test_atlas_runtime_status_panel_contract.py
node --check web/js/atlas_claude_panel.js
```

### CS13: First-class Claude-like Kasane CLI package

Goal: replace the raw script feel with a first-class interactive CLI cockpit.

Implementation tasks:

1. Add package:

```text
kasane_cli/__init__.py
kasane_cli/__main__.py
kasane_cli/client.py
kasane_cli/commands.py
kasane_cli/repl.py
kasane_cli/render.py
kasane_cli/banner.py
```

2. Move reusable HTTP client logic from `scripts/atlas_run_cli.py` into `kasane_cli/client.py`.
3. Keep `scripts/atlas_run_cli.py` as a thin compatibility wrapper.
4. Implement non-interactive commands with `--json` support.
5. Implement interactive REPL:
   - banner;
   - project detection;
   - server health check;
   - slash command parser;
   - natural-language plan creation;
   - active pool/run memory;
   - event streaming with concise stage rendering;
   - graceful Ctrl-C handling.
6. Add redaction in render layer for secret-looking keys.
7. Optional: if dependencies allow, use only stdlib first. Do not add heavy TUI dependencies in this package.

Acceptance:

- `python -m kasane_cli --help` works.
- `python -m kasane_cli status --json` is machine-readable and banner-free.
- `python -m kasane_cli` opens interactive mode with banner and prompt.
- `/plan`, `/run`, `/watch`, `/retry`, `/revise`, `/cancel`, `/exit` work through the Run API.
- Tests prove CLI does not call direct patch/apply/verify endpoints.

Suggested tests:

```text
python -m pytest -q tests/test_kasane_cli.py
python -m py_compile kasane_cli/__main__.py kasane_cli/client.py kasane_cli/repl.py kasane_cli/render.py kasane_cli/banner.py scripts/atlas_run_cli.py
```

### CS14: KasaneCore ASCII startup banner

Goal: show KasaneCore identity at CLI/server startup without breaking automation.

Implementation tasks:

1. Add shared banner module:

```text
app/startup_banner.py
kasane_cli/banner.py
```

2. Use a single source of truth for banner text where practical.
3. CLI interactive mode prints banner by default.
4. Server startup prints banner only when:
   - process is interactive or env allows it;
   - not under pytest;
   - not `KASANE_NO_BANNER=1`;
   - not JSON/log-machine mode.
5. Suggested env controls:

```text
KASANE_NO_BANNER=1
KASANE_BANNER=0|1
NO_COLOR=1
```

6. Ensure Windows/Linux terminals render safely.

Acceptance:

- Banner appears in interactive CLI.
- Banner can be disabled.
- JSON mode never includes banner.
- Tests cover banner text and suppression.

Suggested tests:

```text
python -m pytest -q tests/test_kasane_startup_banner.py
```

### CS15: Live validation for hardened run control and CLI

Goal: validate the new hardening with 8080 LLM and real backend run paths.

Use:

```text
http://127.0.0.1:8080/v1
```

Required scenarios:

1. API starts run, CLI watches, browser-status-compatible endpoint observes.
2. CLI interactive-style command starts run, API watches.
3. Failed item retry uses `/runs/{run_id}/retry` and completes or truthfully fails.
4. Resume without client-provided `item_ids` skips completed item and runs remaining item.
5. Duplicate start attempt is rejected or idempotent.
6. Stale running run recovery marks blocked/retryable, not success.
7. Banner appears in interactive mode and is absent in JSON mode.

If 8080 is unavailable, record `blocked_live_llm_unavailable`, not passed.

Suggested runner:

```text
tools/run_atlas_run_control_hardening_eval.py
```

### CS16: Final evidence review and docs closeout

Goal: final deterministic + LLM-assisted evidence review.

Implementation tasks:

1. Extend or add final review mode in:

```text
tools/run_atlas_run_control_hardening_eval.py
```

2. Evidence bundle must include:
   - focused test outputs;
   - run state JSON excerpts;
   - event log excerpts;
   - retry/revise evidence;
   - item-selection evidence showing backend-owned order;
   - duplicate-start/lease evidence;
   - CLI transcript excerpts with secrets redacted;
   - banner JSON/no-banner evidence;
   - live scenario JSON;
   - unavailable checks, if any.
3. Ask 8080 LLM to review only after deterministic checks pass.
4. LLM review is advisory and can block only on concrete contradictory evidence or missing deterministic checks.
5. Update this plan's status table.

Acceptance:

- All CS9-CS15 acceptance checks passed or truthfully blocked.
- Final review report written.
- AGENTS.md points to this plan as complete or next package is clearly stated.

## Status

| Package | Goal | Status | Evidence |
|---|---|---|---|
| CS9 | Run retry/revise backend execution | completed | `tests/test_atlas_run_retry_revise.py`; focused/affected 38 passed; 8080 model endpoint reachable |
| CS10 | Backend-owned item ordering and resume target selection | completed | `tests/test_atlas_run_item_selection.py`; focused/affected 51 passed; UI/CLI omit normal `item_ids` |
| CS11 | Run leases, duplicate-start guard, restart recovery | pending | |
| CS12 | Remove or hard-disable legacy UI orchestration | pending | |
| CS13 | First-class Claude-like Kasane CLI package | pending | |
| CS14 | KasaneCore ASCII startup banner | pending | |
| CS15 | Live 8080 validation | pending | |
| CS16 | Final evidence review and docs closeout | pending | |

## Completion Evidence

### CS9 — Run retry/revise backend execution (completed 2026-06-25)

Status: completed locally; PR pending

Changed files:

- `agent/atlas_run_retry_policy.py`
- `agent/atlas_run_schema.py`
- `agent/atlas_run_store.py`
- `app/api/atlas_runs.py`
- `scripts/atlas_run_cli.py`
- `web/js/atlas_claude_panel.js`
- `web/js/atlas_pipeline_api.js`
- `tests/test_atlas_run_retry_revise.py`
- `tests/test_atlas_run_api.py`
- `tests/test_atlas_run_cli.py`
- `tests/test_atlas_runtime_status_panel_contract.py`
- `docs/atlas_run_control_cli_banner_plan.md`

Validation:

- `python -m pytest -q tests/test_atlas_run_retry_revise.py tests/test_atlas_run_api.py tests/test_atlas_run_cli.py tests/test_atlas_runtime_status_panel_contract.py` -> 24 passed
- `python -m pytest -q tests/test_atlas_run_orchestrator.py tests/test_atlas_run_retry_revise.py tests/test_atlas_run_api.py tests/test_atlas_run_cli.py tests/test_atlas_runtime_status_panel_contract.py tests/test_atlas_server_controlled_flow_eval.py` -> 38 passed
- `python -m py_compile app/api/atlas_runs.py agent/atlas_run_orchestrator.py agent/atlas_run_store.py agent/atlas_run_schema.py agent/atlas_run_retry_policy.py` -> passed
- `python -m py_compile app/api/atlas_runs.py agent/atlas_run_schema.py agent/atlas_run_store.py agent/atlas_run_retry_policy.py scripts/atlas_run_cli.py tests/test_atlas_run_retry_revise.py` -> passed
- `node --check web/js/atlas_claude_panel.js; node --check web/js/atlas_pipeline_api.js` -> passed

8080 evidence: `GET http://127.0.0.1:8080/v1/models` returned model `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`. CS9 adds no new LLM-backed generation path, so no live patch-generation replay is counted as CS9 acceptance evidence.

Behavior implemented: `/api/atlas/runs/{run_id}/retry` now validates retry mode, enforces a backend retry budget, rejects completed/cancelled runs unless explicit `mode=rerun`, records `retry_count` / `max_retries` / `last_retry_reason`, emits `run_retry_requested` and `run_retry_started`, and starts backend `resume` or `rerun` orchestration. `/revise` records a first-class revision note and user-action state without falsely claiming execution started.

Safety invariants: retry/revise remain backend Run API operations; UI and CLI only send user intent. Retry resumes through `AtlasRunOrchestrator` and therefore preserves Proposal / Safe Apply / Verification boundaries. Revise does not mark unavailable or unexecuted work as passed.

Remaining gaps: CS10 backend-owned item ordering and resume target selection, CS11 leases/recovery, CS12 hard-disable legacy UI orchestration, CS13 first-class CLI, CS14 banner, CS15 live hardening validation, CS16 final evidence review.

Next package: CS10 — Backend-owned item ordering and resume target selection

Blocker: none

Proof level: `run_retry_revise_backend_execution_complete`

### CS10 — Backend-owned item ordering and resume target selection (completed 2026-06-25)

Status: completed locally; PR pending

Changed files:

- `agent/atlas_run_selection.py`
- `agent/atlas_run_orchestrator.py`
- `app/api/atlas_runs.py`
- `scripts/atlas_run_cli.py`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_run_item_selection.py`
- `tests/test_atlas_run_cli.py`
- `tests/test_atlas_runtime_status_panel_contract.py`
- `docs/atlas_run_control_cli_banner_plan.md`

Validation:

- `python -m pytest -q tests/test_atlas_run_item_selection.py tests/test_atlas_run_orchestrator.py tests/test_atlas_run_api.py tests/test_atlas_run_cli.py tests/test_atlas_runtime_status_panel_contract.py` -> 33 passed
- `python -m pytest -q tests/test_atlas_run_item_selection.py tests/test_atlas_run_orchestrator.py tests/test_atlas_run_api.py tests/test_atlas_run_cli.py tests/test_atlas_runtime_status_panel_contract.py tests/test_atlas_server_controlled_ui_cli_sc0.py tests/test_atlas_dev_phase_llm_progress_indicator_contract.py tests/test_atlas_server_controlled_flow_eval.py` -> 51 passed
- `python -m py_compile agent/atlas_run_selection.py agent/atlas_run_orchestrator.py app/api/atlas_runs.py scripts/atlas_run_cli.py tests/test_atlas_run_item_selection.py tests/test_atlas_run_api.py` -> passed
- `node --check web/js/atlas_claude_panel.js; node --check web/js/atlas_pipeline_api.js` -> passed
- `git diff --check` -> passed, with CRLF warnings only

8080 evidence: `GET http://127.0.0.1:8080/v1/models` returned model `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`. CS10 adds no new LLM-backed generation path, so no live patch-generation replay is counted as CS10 acceptance evidence.

Behavior implemented: added backend `select_run_items()` for fresh/resume/rerun/explicit item selection. Normal UI approval no longer fetches PlanPool to build `item_ids`, and CLI `start` omits `item_ids` unless the operator explicitly provides them. Backend `run_items()` emits `run_items_selected` with selected order and then executes one item at a time against the current workspace state.

Safety invariants: UI and CLI no longer own normal item order or resume target selection. Explicit item selection remains available for manual/advanced use, while backend selection skips completed run/pool items on resume and keeps blocked/non-runnable items out of automatic execution.

Remaining gaps: CS11 leases/recovery, CS12 hard-disable legacy UI orchestration, CS13 first-class CLI, CS14 banner, CS15 live hardening validation, CS16 final evidence review.

Next package: CS11 — Run leases, duplicate-start guard, and restart recovery

Blocker: none

Proof level: `backend_item_selection_complete`

## Required focused test matrix

As packages land, add or update:

```text
python -m pytest -q tests/test_atlas_run_retry_revise.py
python -m pytest -q tests/test_atlas_run_item_selection.py
python -m pytest -q tests/test_atlas_run_lease_recovery.py
python -m pytest -q tests/test_atlas_ui_no_legacy_orchestration.py
python -m pytest -q tests/test_kasane_cli.py
python -m pytest -q tests/test_kasane_startup_banner.py
python -m pytest -q tests/test_atlas_run_control_hardening_eval.py
```

Keep running existing affected tests:

```text
python -m pytest -q tests/test_atlas_run_api.py
python -m pytest -q tests/test_atlas_run_orchestrator.py
python -m pytest -q tests/test_atlas_run_cli.py
python -m pytest -q tests/test_atlas_runtime_status_panel_contract.py
python -m pytest -q tests/test_atlas_server_controlled_flow_eval.py
```

Also run syntax checks:

```text
python -m py_compile app/api/atlas_runs.py agent/atlas_run_orchestrator.py agent/atlas_run_store.py
python -m py_compile kasane_cli/__main__.py kasane_cli/client.py kasane_cli/repl.py kasane_cli/render.py kasane_cli/banner.py
node --check web/js/atlas_claude_panel.js
node --check web/js/atlas_pipeline_api.js
```

## Completion definition

This track is complete only when:

- retry/revise are real backend control-plane operations or explicitly blocked with truthful state;
- UI no longer sends normal `item_ids` or owns item order;
- backend prevents duplicate concurrent starts;
- stale running runs are inspectable and retryable after restart;
- legacy UI orchestration is removed or impossible to invoke;
- `python -m kasane_cli` provides a Claude-like interactive cockpit;
- CLI JSON mode is automation-safe and banner-free;
- KasaneCore ASCII banner appears in interactive startup and can be disabled;
- 8080 live validation passes or truthfully blocks;
- final evidence review is written.
