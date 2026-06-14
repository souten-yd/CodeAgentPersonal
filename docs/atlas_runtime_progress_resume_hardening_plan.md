# Atlas Runtime Progress and Resume/Rehydrate Hardening Plan

## Purpose

This plan addresses a blocking Atlas UI/runtime observability bug:

```text
Atlas Plan is generated, approved, and execution/development starts.
However, current LLM generation progress is not shown in the indicator.
The indicator appears stopped.
Browser log:
[ctx] Could not fetch llm props: Cannot access '_current_n_ctx_ui' before initialization

After switching tabs or browser reload, returning to Atlas can show only the green frame/shell.
Development status and token generation indicator are missing.
```

This is not only a cosmetic problem. It prevents the user from knowing whether Atlas is generating, stalled, disconnected, reconnecting, or completed.

## Baseline Observations

The UI already contains token indicator elements in `ui.html`, including `tok-display`, `tok-total`, and `tok-tps`. The Atlas conversational shell also contains `atlas-claude-transcript`, which means the DOM has a place to show progress and transcript state. The API layer has Atlas pipeline/run response structures including `ContinuationResponse`, which means the backend already has concepts needed for restoring run state.

The current failure therefore appears to be in one or more of these layers:

1. Frontend JavaScript initialization order.
2. LLM props/context polling.
3. Progress event production from LLM calls.
4. Progress event transport to the UI.
5. Durable server-side run status replay after tab switch/reload.
6. Atlas shell rehydration after browser reload.

## Root Cause Hypothesis

### H1. `_current_n_ctx_ui` TDZ / initialization-order bug

The warning:

```text
[ctx] Could not fetch llm props: Cannot access '_current_n_ctx_ui' before initialization
```

is characteristic of JavaScript temporal dead zone behavior. A `let` or `const` binding named `_current_n_ctx_ui` is read before its declaration has completed.

Likely patterns:

```javascript
refreshLLMProps();        // calls code that reads _current_n_ctx_ui
let _current_n_ctx_ui = 0;
```

or:

```javascript
const props = await fetchLLMProps();
if (props.n_ctx !== _current_n_ctx_ui) { ... }
let _current_n_ctx_ui = props.n_ctx;
```

or an initialization cycle caused by inline scripts, settings modal startup, periodic polling, and Atlas shell startup.

Required fix:

- Move all LLM context state declarations to the top-level before any startup hooks, timers, event handlers, or async polls can run.
- Prefer an explicit state object initialized once:

```javascript
const LLM_CONTEXT_STATE = {
  currentNctxUi: null,
  currentModel: "",
  lastPropsAt: 0,
  lastError: "",
  initialized: false
};
```

- Never read raw `_current_n_ctx_ui` before initialization.
- Wrap LLM props fetch errors so one props failure cannot stop Atlas progress rendering.
- Add a startup test that imports/executes the UI script and calls init functions in realistic order.

### H2. Progress indicator not connected to execution-phase LLM calls

Atlas may have progress display for normal chat or plan generation, but not for approved execution/development phases. The execution path can involve:

- patch proposal generation;
- repair generation;
- self-correction;
- verification recommendation;
- Nexus context summarization;
- Project Intelligence prompt construction;
- Forge model execution bridge.

All LLM calls used by Atlas should report progress to a shared event sink. The indicator must not depend only on chat token metrics.

Required fix:

- Add a unified `AtlasLLMProgressEvent` shape.
- Ensure every Atlas LLM path can pass `on_progress` to `AtlasLLMJsonAdapter` or an equivalent model execution bridge.
- Persist progress summaries in the Atlas journal/checkpoint so reload can show last known state.
- UI should display the active Atlas phase, model, tokens, tps, elapsed, last progress time, and current run id.

### H3. Browser reload loses ephemeral frontend state

After reload, local JS variables and in-memory event subscriptions are lost. If Atlas relies on frontend memory to know current pool/run/item/generation, it will show an empty shell or green frame.

Required fix:

- Server is authoritative.
- LocalStorage may only be a hint for `workspace_id`, `pool_id`, and `run_id`.
- On Atlas tab mount/reload, the UI must call a resume endpoint to fetch the latest active or last run state.
- The UI must reconstruct the current Atlas transcript/status from:
  - PlanPool state;
  - checkpoint state;
  - journal events;
  - latest progress snapshot;
  - current item/proposal/verification state;
  - continuation response.

### H4. Reconnection does not replay missed events

If the tab is backgrounded or the browser reloads, the SSE/WebSocket/polling connection is gone. On return, the UI must replay missed events from server-side storage or fetch a current snapshot.

Required fix:

- Maintain a monotonically increasing event sequence number or timestamp.
- UI stores last seen sequence in localStorage.
- On reconnect, UI requests events since last seen sequence or fetches a compact snapshot.
- If replay is unavailable, UI still renders a truthful snapshot:
  - active;
  - reconnecting;
  - stalled;
  - terminal;
  - unknown with reason.

## Target Architecture

### Backend: Progress Event Model

Add a durable progress event model for Atlas runtime/development phases.

Suggested event shape:

```json
{
  "event_id": "uuid",
  "sequence": 123,
  "timestamp": "2026-06-14T10:05:31Z",
  "workspace_id": "default",
  "pool_id": "pool_x",
  "run_id": "run_y",
  "item_id": "item_z",
  "phase": "patch_generation",
  "source": "atlas_llm",
  "model": "local-llm",
  "status": "running",
  "event_type": "llm_token_delta",
  "tokens_total": 128,
  "tokens_delta": 8,
  "tokens_per_second": 12.5,
  "first_token_seen": true,
  "first_token_at": "2026-06-14T10:05:40Z",
  "last_progress_at": "2026-06-14T10:05:50Z",
  "message": "Generating patch proposal",
  "metadata": {}
}
```

Statuses:

```text
starting
waiting_first_token
running
reconnecting
stale
stalled
completed
failed
cancelled
unknown
```

Event types:

```text
llm_started
llm_waiting_first_token
llm_first_token
llm_token_delta
llm_heartbeat
llm_idle_waiting
llm_completed
llm_failed
llm_stalled_before_first_token
llm_stalled_after_progress
llm_total_timeout
atlas_run_started
atlas_item_started
atlas_item_completed
atlas_item_failed
atlas_run_completed
atlas_run_failed
atlas_snapshot_replayed
```

### Backend: Progress Snapshot Endpoint

Add or harden an endpoint that returns a compact current snapshot:

```text
GET /api/atlas/runtime/snapshot?workspace_id=default&pool_id=...&run_id=...
```

Response shape:

```json
{
  "workspace_id": "default",
  "pool_id": "pool_x",
  "run_id": "run_y",
  "status": "running",
  "current_item_id": "item_z",
  "current_phase": "patch_generation",
  "current_message": "Generating patch proposal",
  "last_event_sequence": 123,
  "last_event_at": "2026-06-14T10:05:50Z",
  "llm": {
    "model": "local-llm",
    "status": "running",
    "tokens_total": 128,
    "tokens_per_second": 12.5,
    "first_token_seen": true,
    "last_progress_at": "2026-06-14T10:05:50Z"
  },
  "plan_pool": {},
  "warnings": [],
  "errors": []
}
```

If an existing continuation endpoint can provide this, extend it rather than creating a duplicate.

### Backend: Event Replay Endpoint

Add or harden:

```text
GET /api/atlas/runtime/events?workspace_id=default&pool_id=...&run_id=...&after_sequence=...
```

This may be backed by Atlas journal NDJSON, checkpoint events, or a new compact progress event file.

### Frontend: Startup and Rehydrate Flow

On page load or Atlas mode switch:

1. Initialize all global state objects first.
2. Register DOM references after DOMContentLoaded.
3. Read localStorage hint:
   - `atlas_workspace_id`;
   - `atlas_last_pool_id`;
   - `atlas_last_run_id`;
   - `atlas_last_event_sequence`.
4. Call runtime snapshot endpoint.
5. Render a truthful state:
   - active run with item/progress;
   - completed run;
   - failed run;
   - reconnecting;
   - no active run.
6. Replay events since last seen sequence.
7. Start live subscription or polling.
8. If subscription fails, show reconnecting/stale status, not an empty green frame.

### Frontend: Indicator Rules

The token indicator must show:

- hidden only when no active LLM and no recent LLM activity;
- waiting state before first token;
- active token count and tps during generation;
- stale/reconnecting when last progress is old but run is active;
- stalled when backend says stalled;
- completed for a short grace period after terminal.

The Atlas development status card must show:

- pool id;
- run id;
- current item;
- current phase;
- current message;
- last event time;
- reconnect status;
- next action or terminal result.

## Package Sequence

### AUIR-1: Fix LLM props initialization and token indicator safety

Scope:

- Locate `_current_n_ctx_ui` declaration and all reads/writes.
- Replace raw TDZ-prone variable usage with an initialized state object.
- Move declarations before startup hooks/timers.
- Ensure props fetch failure does not abort Atlas UI init.
- Add guard logging with actionable detail.

Acceptance:

- No browser startup path can throw `Cannot access '_current_n_ctx_ui' before initialization`.
- Failed LLM props fetch shows warning but does not stop Atlas state rendering.
- Token indicator can still render run progress even if props are unavailable.
- Focused JS/browser smoke covers initialization order.

### AUIR-2: Durable Atlas run progress event model

Scope:

- Add progress event schema or normalize existing event records.
- Attach progress sink to Atlas LLM calls used by plan, approved execution, patch generation, repair, and verification recommendation.
- Persist latest progress snapshot.
- Preserve existing journal/checkpoint behavior.

Acceptance:

- Starting approved execution writes `atlas_run_started`.
- LLM generation writes `llm_started`, `llm_first_token`, `llm_token_delta`, and terminal event.
- Latest progress survives browser reload.
- Events contain workspace/pool/run/item/phase identifiers.

### AUIR-3: Atlas tab reload/resume rehydration

Scope:

- Add or harden runtime snapshot endpoint.
- Add event replay endpoint if missing.
- On Atlas tab mount/reload, fetch server-authoritative state.
- Rebuild transcript/status cards from snapshot and replayed events.
- Store only hints in localStorage.

Acceptance:

- During an active run, browser reload returns to Atlas with current status visible.
- Switching to another tab and back resumes progress display.
- If run completed while tab was away, terminal state is shown.
- Empty green frame is never shown for a known active/terminal run.

### AUIR-4: Live indicator reconnection and stale/stalled state UX

Scope:

- Implement connection states:
  - live;
  - reconnecting;
  - stale;
  - stalled;
  - terminal;
  - unknown.
- Add last-progress age display.
- Make reconnection retry bounded and visible.
- Avoid duplicate event rendering.

Acceptance:

- Killing/restarting connection shows reconnecting/stale, then resumes.
- Backend stalled state is displayed distinctly from disconnected UI.
- Duplicate events do not duplicate transcript/status lines.

### AUIR-5: Regression tests and mobile/browser reload smoke

Scope:

- Add frontend init test for `_current_n_ctx_ui`.
- Add reload/resume test for Atlas active run.
- Add progress event replay test.
- Add mobile viewport smoke if existing Playwright infrastructure supports it.

Acceptance:

- Regression test fails on the old TDZ bug.
- Reload/resume test fails on old green-frame-only behavior.
- All new tests pass with the fix.

### AUIR-6: Return to PIBIH-1 LLM planning timeout hardening

After Atlas runtime progress and reload/resume are fixed, continue the previous PIBIH sequence:

```text
PIBIH-1: LLM Planning Timeout and Streaming Progress Hardening
PIBIH-2: Impact Analysis Core
PIBIH-3: Deep Behavioral Graph V3
PIBIH-4: Project Intelligence Planning and Generation Injection
PIBIH-5: Plan-Time Nexus Web Research
PIBIH-6: Impact UI / Planner Exposure
PIBIH-7: Runtime Evidence Promotion and Historical Risk Memory
```

## Implementation Notes

### Do not rely on frontend memory

The Atlas UI must not depend on an in-memory JS variable to know that a run is active. Browser reload loses memory.

Use localStorage only for hints. Server state is authoritative.

### Do not let props fetch failure break Atlas

LLM props such as context size are useful but non-critical. If props fetch fails, the UI should still display active run progress.

### Do not claim live model evidence from mock progress

Tests can use mock progress for deterministic assertions, but status docs must mark live model evidence unavailable unless a real model run was performed.

## Completion Criteria

- `_current_n_ctx_ui` warning is gone.
- Atlas token indicator updates during approved development execution.
- Atlas status survives tab switch and reload.
- Green-frame-only state is eliminated.
- Progress state distinguishes waiting, running, reconnecting, stale, stalled, completed, and failed.
- Tests prove initialization, progress replay, and reload/resume.
