# Atlas Close-Safe Codegen / Server-Controlled UI-CLI Plan

> Active track: **CS0-CS8 Close-Safe Codegen**.
>
> Start from root `AGENTS.md`, then read this file. This plan makes Atlas safe when the browser is closed by replacing UI-owned execution with a backend run control plane and by adding a CLI that observes and decides through the same API.

## Naming

This work package sequence is named **CS0-CS8**.

```text
CS = Close-Safe Codegen / Client-Safe Control
```

Earlier notes may have used `SC0-SC8`. Treat those as the same track. From this document forward, use **CS0-CS8**.

## Final goal

Atlas must keep generating and managing code safely even when the Web UI is closed, refreshed, hidden on mobile, or replaced by a CLI.

The target split is:

```text
Backend = execution authority, state machine, progress log, recovery source
Web UI  = lightweight viewer plus user-decision sender
CLI     = lightweight viewer plus user-decision sender
```

The Web UI and CLI must use the same backend `run_id`. Neither client may run its own Plan -> Patch -> Apply -> Verify loop.

## Current problem to remove

Current code already has server-side pieces: read-only workflow state, async PlanPool creation, runtime progress events, recovery summaries, Safe Apply, verification, and multi-item autopilot.

However, `web/js/atlas_claude_panel.js` still contains `approveAndRunPipeline()`, which fetches the PlanPool, approves items, generates patch proposals, approves proposals, calls apply/verify, polls sub-progress, and classifies the final result in browser JavaScript.

That means browser lifetime can affect execution. CS0-CS8 moves that orchestration into the backend.

## Non-negotiable rules

Preserve all root `AGENTS.md` safety rules:

- no bypass around Proposal, Safe Apply, or Verification;
- unavailable evidence is not passed evidence;
- mock output is not live evidence;
- UI rendering is not runtime evidence;
- Project Intelligence and Twin remain advisory, not execution authority;
- external providers remain policy-gated;
- remote publication still requires explicit user authorization.

Additional rules for CS0-CS8:

- UI and CLI must call `/api/atlas/runs/*` for execution.
- Backend owns item order, retry budget, resume skip logic, phase transition, and terminal status.
- UI and CLI may only send user intent: approve, revise, cancel, retry, answer clarification.
- All progress must be replayable from backend event logs after client restart.
- A browser close/reload must not cancel or corrupt an in-progress backend run.

## Target API

Add a backend Run API:

```text
POST /api/atlas/runs
GET  /api/atlas/runs/{run_id}
GET  /api/atlas/runs/{run_id}/status
GET  /api/atlas/runs/{run_id}/events?after_sequence=N
POST /api/atlas/runs/{run_id}/decisions
POST /api/atlas/runs/{run_id}/cancel
POST /api/atlas/runs/{run_id}/retry
POST /api/atlas/runs/{run_id}/revise
```

`POST /api/atlas/runs` returns quickly with a `run_id`. Long work runs under backend control. Clients watch events.

Minimal create payload:

```json
{
  "pool_id": "pool_xxx",
  "workspace_id": "default",
  "project_path": "",
  "mode": "fresh|resume|rerun",
  "decision": "approve",
  "metadata": {}
}
```

Minimal response:

```json
{
  "run_id": "atlas_run_xxx",
  "pool_id": "pool_xxx",
  "status": "queued|running",
  "events_after_sequence": 0
}
```

## Backend state

Create small schema/store modules first, then orchestrator.

Likely files:

```text
agent/atlas_run_schema.py
agent/atlas_run_store.py
agent/atlas_run_events.py
agent/atlas_run_orchestrator.py
app/api/atlas_runs.py
```

State must include at least:

```text
run_id, pool_id, workspace_id, status, phase,
current_item_id, current_item_index, total_items,
completed_item_ids, failed_item_ids, blocked_item_ids, skipped_item_ids,
requires_user_action, block_reason, error, next_actions,
created_at, updated_at, finished_at, metadata
```

Events must include monotonic sequence and be readable by cursor:

```text
sequence, run_id, pool_id, event_type, phase, status, item_id,
message, source, created_at, metadata
```

Storage should reuse `AtlasJournal` conventions where practical. Do not create a second unrelated persistence model unless necessary.

## CLI target

Add a thin HTTP client after the Run API exists.

Suggested layout:

```text
atlasctl/__main__.py
atlasctl/client.py
atlasctl/render.py
```

Initial commands:

```text
python -m atlasctl status
python -m atlasctl plan "..."
python -m atlasctl pools list
python -m atlasctl pool show <pool_id>
python -m atlasctl run <pool_id>
python -m atlasctl watch <run_id>
python -m atlasctl events <run_id> --after N
python -m atlasctl decide <run_id> --type approve|revise|cancel --note "..."
python -m atlasctl cancel <run_id>
python -m atlasctl retry <run_id>
```

Default server URL:

```text
ATLAS_BASE_URL=http://127.0.0.1:8000
```

CLI must not call patch proposal, Safe Apply, verification, or autopilot endpoints directly.

## CS0-CS8 work packages

Execute these packages in order. Each package must update the status table in this document with truthful evidence.

### CS0: Baseline proof

Freeze the current gap before changing behavior.

Inspect:

```text
web/js/atlas_claude_panel.js
web/js/atlas_pipeline_api.js
app/api/atlas_pipeline.py
app/api/atlas_workflow_state.py
app/atlas/workflow_state_contract.py
agent/atlas_journal.py
agent/atlas_pipeline_runner.py
```

Required tests:

- prove `approveAndRunPipeline()` currently calls direct patch/apply/verify endpoints;
- prove existing pipeline events support replay cursor;
- prove workflow-state endpoint is read-only/backend-authoritative.

Acceptance:

- No runtime behavior change in CS0.
- The current UI-owned execution gap is pinned by tests.

### CS1: Run schema/store/events

Add run state and event primitives.

Acceptance:

- create/load/save run state;
- append/read events after sequence;
- invalid ids are rejected;
- terminal states are not changed by heartbeat-only patches;
- focused unit tests pass.

### CS2: Run API skeleton

Expose `/api/atlas/runs/*` without moving full orchestration yet.

Acceptance:

- create run returns `run_id` quickly;
- status/events/cancel/decisions endpoints work;
- decisions are recorded as events only and do not bypass gates;
- existing PlanPool/recovery/UI tests still pass.

### CS3: RunOrchestrator MVP

Move one-item execution to backend.

Required flow:

```text
load PlanPool
check clarification / critical / safety blockers
approve plan item through existing approval service
generate patch proposal
approve patch proposal through existing proposal service
apply and verify through existing services
emit events and save state after every phase
```

Acceptance:

- one low-risk item can complete through Run API;
- failure becomes failed/blocked, not success;
- status/events survive client disappearance.

### CS4: Multi-item resume/retry/rerun

Move the current interleaved UI loop into backend.

Required behavior:

- process one item at a time: generate -> approve -> apply/verify -> next;
- generate each next patch against current workspace after earlier edits;
- already-applied items are skipped by backend state;
- `mode=resume` continues safely;
- `mode=rerun` resets explicit execution state and records the reset;
- retry budget is backend-owned;
- cancel is checked between expensive phases.

Acceptance:

- two items editing the same file avoid edit drift;
- resume after one completed item works;
- generation failure before first patch is an honest terminal failure;
- partial completion is not reported as full success.

### CS5: CLI thin client

Add CLI using the same Run API.

Acceptance:

- CLI can plan, list/show pools, start run, watch events, submit decisions, cancel, retry;
- CLI can be killed and restarted, then `watch <run_id>` resumes from server events;
- tests prove CLI does not call patch/apply/verify endpoints.

### CS6: UI thinning

Replace browser orchestration with Run API calls.

Acceptance:

- approval button calls `POST /api/atlas/runs`;
- UI renders `/runs/{run_id}/status` and `/events`;
- UI sends decisions to `/runs/{run_id}/decisions`;
- UI no longer directly calls `generatePatchProposal`, `decidePatchProposal`, or `runMultiItemAutopilot` in the approval path;
- reload mid-run restores from backend state.

### CS7: Live 8080 weak-LLM validation

Use the user's OpenAI-compatible LLM on:

```text
http://127.0.0.1:8080/v1
```

Required live checks:

1. Web app greenfield: plan -> run -> apply -> verify.
2. Existing Web app repair: seeded defect -> run -> verify fix.
3. Business/config scenario: bounded edit -> deterministic check.
4. CLI starts a run and UI/status API can observe it.
5. UI/API starts a run and CLI can watch it.

If the model is unavailable, record `blocked_live_llm_unavailable`; do not mark the package complete.

### CS8: Final LLM evaluation

After deterministic tests and live checks, ask the 8080 LLM to review the evidence bundle.

Create or update a runner such as:

```text
tools/run_atlas_server_controlled_flow_eval.py
```

The evidence bundle must include:

- focused test outputs;
- run state JSON;
- event log excerpts;
- final report excerpts;
- live scenario result JSON;
- unavailable checks, if any.

The LLM must evaluate whether:

- UI and CLI are thin clients;
- backend owns phase transitions and retry policy;
- client restart does not lose execution state;
- Safe Apply and verification evidence are real;
- no success depends on mock output, UI rendering, or unavailable evidence.

LLM review is advisory. It blocks completion only when it identifies concrete contradictory evidence or a missing deterministic check.

## Test matrix

Focused tests to add/use as packages land:

```text
python -m pytest -q tests/test_atlas_reload_resume_progress_ui_contract.py
python -m pytest -q tests/test_atlas_run_schema.py
python -m pytest -q tests/test_atlas_run_api.py
python -m pytest -q tests/test_atlas_run_orchestrator.py
python -m pytest -q tests/test_atlas_cli.py
```

Also run affected tests for PlanPool API, approvals, patch proposal generation, Safe Apply, auto verification, multi-item autopilot, recovery/continuation, and UI contract checks.

## Status

| Package | Goal | Status | Evidence |
|---|---|---|---|
| CS0 | Baseline proof | pending | |
| CS1 | Run schema/store/events | pending | |
| CS2 | Run API skeleton | pending | |
| CS3 | RunOrchestrator MVP | pending | |
| CS4 | Multi-item resume/retry/rerun | pending | |
| CS5 | CLI thin client | pending | |
| CS6 | UI thinning | pending | |
| CS7 | Live 8080 weak-LLM validation | pending | |
| CS8 | Final LLM evaluation | pending | |

## Completion definition

Complete only when browser lifetime no longer controls execution:

- Web UI starts/observes backend runs only;
- CLI starts/observes the same backend runs;
- run progress survives browser close, refresh, and CLI exit;
- backend events replay all important progress;
- deterministic tests pass;
- 8080 live LLM checks pass or truthfully block completion;
- final evidence review report is written.
