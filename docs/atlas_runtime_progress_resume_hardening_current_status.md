# Atlas Runtime Progress and Resume/Rehydrate Hardening Current Status

## Track

AUIR: Atlas UI Runtime Progress and Resume/Rehydrate Hardening

## Overall Status

```text
status: in_progress
current_package: AUIR-3
next_action: implement Atlas tab reload/resume rehydration from server-authoritative progress state
```

## User-Observed Bug

```text
Atlasでプラン生成後、承認して実行する。
その後開発を実行するが、現状のLLMの生成状況がインジケータに表示されない。
インジケーターは停止している状況であった。

Log:
10:05:31 WARN [ctx] Could not fetch llm props: Cannot access '_current_n_ctx_ui' before initialization

別タブ移動やブラウザリロード後にAtlasへ戻ると、緑の枠だけ出てくる。
開発状況の表示やトークン生成のインジケータが一切表示されない。
```

## Current Hypothesis

1. `_current_n_ctx_ui` is read before initialization, probably due to JS TDZ with `let`/`const`.
2. LLM props fetch failure may abort or interrupt UI startup chain.
3. Approved Atlas execution/development LLM calls are not attached to the same progress indicator path as chat/plan.
4. Atlas shell state is ephemeral and not fully rehydrated from backend after reload.
5. Missed progress events are not replayed after reconnect.

## Active Package

### AUIR-3: Atlas tab reload/resume rehydration

### Required Code Investigation

Search and inspect:

```text
setMode('atlas')
mobSwitch('atlas')
DOMContentLoaded
window.onload
localStorage
atlas_claude_last_pool_id
atlas_claude_last_goal
getRecoveryLatest
getRecoveryPool
getContinuationLatest
getContinuationPool
getPlanRuntimeStatus
getPipelineStatus
getPipelineEvents
progress_events
latest_progress
atlas-claude-transcript
atlas-llm-progress-line
```

### Acceptance Checklist

- [ ] During an active run, browser reload returns to Atlas with current status visible.
- [ ] Switching to another tab and back resumes progress display.
- [ ] If a run completed while the tab was away, terminal state is shown.
- [ ] Empty green frame is never shown for a known active/terminal run.
- [ ] Current status doc is updated with changed files and evidence.

## Evidence Log Template

Append one block per package completion:

```text
Completed package:
Status:
Changed modules/files:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Real model evidence:
Atlas UI evidence:
Reload/resume evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
```

## Evidence Log

```text
Completed package: AUIR-1 Fix LLM props initialization and token indicator safety
Status: completed
Changed modules/files:
- ui.html
- web/js/atlas_claude_panel.js
- tests/test_atlas_ui_llm_props_init.py
- docs/atlas_runtime_progress_resume_hardening_current_status.md
Behavior implemented:
- Replaced the TDZ-prone `let _current_n_ctx_ui` binding with early initialized `LLM_CONTEXT_STATE` plus get/set helpers.
- Added a compatibility `globalThis._current_n_ctx_ui` accessor without relying on a late lexical binding.
- Replaced raw context-size reads in progress card rendering/timer coloring with `getCurrentNctxUi()`.
- Made LLM props fetch failure non-fatal by recording `propsAvailable=false` and `lastError` while keeping the fallback context size available.
- Fed Atlas `atlas:llm-progress` token deltas into the shared header token indicator even when `maxCtx`/LLM props are unavailable.
Focused tests:
- `python -m pytest tests\test_atlas_ui_llm_props_init.py tests\test_atlas_dev_phase_llm_progress_indicator_contract.py` -> 9 passed.
Syntax checks:
- `python scripts\check_ui_inline_script_syntax.py` -> passed for 1 inline script block and 16 external script files.
- `git diff --check` -> passed; only Git line-ending warnings for existing Windows checkout behavior.
Affected tests:
- `python -m pytest tests\test_ui_js_dependency_contract.py tests\test_static_js_serving.py` -> 11 passed.
Real model evidence:
- localhost:8080 `/v1/models` returned `Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf`.
- localhost:8080 `/v1/chat/completions` advisory review of the AUIR-1 diff returned `verdict: pass` with no concerns. This is advisory evidence only.
Atlas UI evidence:
- Automated browser/manual Atlas runtime smoke not run for AUIR-1; regression covered by contract tests and JS syntax check.
Reload/resume evidence:
- Not applicable to AUIR-1; AUIR-3 remains responsible for server-authoritative reload/resume.
Project Intelligence evidence:
- Not applicable to AUIR-1.
Impact analysis evidence:
- Not applicable to AUIR-1.
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- Not applicable to AUIR-1.
Unavailable checks:
- No live Atlas plan approval/execution browser smoke was performed in this package.
- No reload/resume smoke was performed in this package.
Safety invariants:
- No Proposal / Safe Apply / Verification path was bypassed.
- No external provider was enabled by default.
- No secrets or generated data persistence paths were changed.
- `unavailable` checks are not marked as passed.
Remaining gaps:
- Durable server-side progress events are still needed for approved execution, replay, and reload recovery.
Next package: AUIR-2 Durable Atlas run progress event model
Blocker: none
```

```text
Completed package: AUIR-2 Durable Atlas run progress event model
Status: completed
Changed modules/files:
- agent/atlas_journal.py
- agent/atlas_llm_json_adapter.py
- app/api/atlas_pipeline.py
- tests/test_atlas_runtime_progress_events.py
- docs/atlas_runtime_progress_resume_hardening_current_status.md
Behavior implemented:
- Added per-run durable `progress_events.ndjson` and `latest_progress.json` storage to AtlasJournal.
- Added replay by `after_sequence` and latest progress snapshot loading.
- Wrote durable planning progress events for async PlanPool generation: `llm_started`, `llm_first_token`, `llm_token_delta`, `llm_heartbeat`, `llm_completed`, and `llm_failed`.
- Wrote durable pipeline run events for dry-run execution: `atlas_run_started` and terminal run events.
- Wrote durable patch generation events for approved development: `atlas_run_started`, `llm_started`, token progress, and terminal LLM events with pool/run/item/model/token fields.
- Returned `progress_events` and `latest_progress` from existing pipeline status/events endpoints and exposed patchgen `latest_progress`.
- Preserved subclass/fake adapter behavior in `AtlasLLMJsonAdapter.with_progress()` by shallow-copying `self` instead of rebuilding a base adapter.
Focused tests:
- `python -m pytest tests\test_atlas_runtime_progress_events.py tests\test_atlas_patch_proposal_watchdog.py tests\test_atlas_llm_json_streaming.py tests\test_atlas_api_pipeline.py -q` -> 50 passed.
Syntax checks:
- `python -m py_compile agent\atlas_journal.py app\api\atlas_pipeline.py agent\atlas_llm_json_adapter.py` -> passed.
- `git diff --check` -> passed; only Git line-ending warnings for existing Windows checkout behavior.
Affected tests:
- Included existing patch proposal watchdog, LLM streaming adapter, and Atlas pipeline API contracts in focused test run.
Real model evidence:
- localhost:8080 `/v1/chat/completions` advisory review of the AUIR-2 diff returned `verdict: pass` with no concerns. This is advisory evidence only.
Atlas UI evidence:
- Not run for AUIR-2; backend progress persistence and replay are covered by API/unit tests.
Reload/resume evidence:
- Durable latest/replay state is implemented server-side; browser reload rehydration remains AUIR-3.
Project Intelligence evidence:
- Not applicable to AUIR-2.
Impact analysis evidence:
- Not applicable to AUIR-2.
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- Portal runtime paths were not changed.
Unavailable checks:
- No live browser reload/resume smoke was performed in this package.
- No live approved Atlas execution through the browser was performed in this package.
Safety invariants:
- Proposal / Safe Apply / Verification boundaries were not bypassed.
- Existing journal/checkpoint/pipeline state persistence remains intact.
- No external provider was enabled by default.
- No secrets or generated data persistence paths were added.
- `unavailable` checks are not marked as passed.
Remaining gaps:
- Frontend Atlas tab reload/mode-switch rehydration must consume the durable progress state.
- Stale/reconnecting/stalled UI distinctions remain AUIR-4.
Next package: AUIR-3 Atlas tab reload/resume rehydration
Blocker: none
```

## Package Queue

```text
AUIR-1: Fix LLM props initialization and token indicator safety
AUIR-2: Durable Atlas run progress event model
AUIR-3: Atlas tab reload/resume rehydration
AUIR-4: Live indicator reconnection and stale/stalled state UX
AUIR-5: Regression tests and mobile/browser reload smoke
AUIR-6: Return to PIBIH-1 LLM planning timeout hardening
```
