# Atlas Runtime Progress and Resume/Rehydrate Hardening Current Status

## Track

AUIR: Atlas UI Runtime Progress and Resume/Rehydrate Hardening

## Overall Status

```text
status: completed
current_package: AUIR-6 (handed off to PIBIH-1)
next_action: continue PIBIH-2 Impact Analysis Core; see docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
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

### AUIR-6: Return to PIBIH-1 LLM planning timeout hardening

### Required Code Investigation

Search and inspect:

```text
docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md
docs/atlas_project_intelligence_behavioral_impact_hardening_plan.md
docs/atlas_project_intelligence_behavioral_impact_hardening_test_plan.md
docs/atlas_project_intelligence_behavioral_impact_hardening_agent_entrypoint.md
LLM planning timeout
streaming progress
phase-specific timeout reason
```

### Acceptance Checklist

- [x] PIBIH status/plan/test/entrypoint docs are read before editing.
- [x] Slow local planning models can complete or fail with phase-specific timeout reasons.
- [x] Streaming planning progress remains visible during long-running LLM calls.
- [x] Local-only and external-provider policy boundaries remain intact.
- [x] Focused tests and live localhost:8080 advisory review are recorded truthfully (see PIBIH-1 evidence in docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md).

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

```text
Completed package: AUIR-3 Atlas tab reload/resume rehydration
Status: completed
Changed modules/files:
- web/js/atlas_pipeline_api.js
- web/js/atlas_claude_panel.js
- tests/test_atlas_reload_resume_progress_ui_contract.py
- docs/atlas_runtime_progress_resume_hardening_current_status.md
Behavior implemented:
- Added `after_sequence` support to the frontend `getPipelineEvents` wrapper.
- Persisted Atlas pool/run/progress sequence hints in localStorage when patch generation starts or progress replay is applied.
- On Atlas activation/project restore, replayed server-authoritative runtime `progress_events` and `latest_progress` for the known pool/run.
- Dispatched restored durable progress into the existing `atlas:llm-progress` indicator path so token totals/tps update after reload.
- Rendered restored runtime progress through the existing status panel payload with a non-empty restored progress message.
- Added planning/restored progress handling so rehydrated planning or patch-generation states do not collapse to an empty frame.
- Isolated replay errors from already-loaded runtime status so a transient replay failure does not erase visible server status.
Focused tests:
- `python -m pytest tests\test_atlas_reload_resume_progress_ui_contract.py tests\test_atlas_dev_phase_llm_progress_indicator_contract.py tests\test_static_js_serving.py tests\test_ui_js_dependency_contract.py -q` -> 23 passed.
Syntax checks:
- `python scripts\check_ui_inline_script_syntax.py` -> passed for 1 inline script block and 16 external script files.
- `git diff --check` -> passed; only Git line-ending warnings for existing Windows checkout behavior.
Affected tests:
- Included existing LLM indicator, static JS serving, and UI JS dependency contracts in focused test run.
Real model evidence:
- localhost:8080 `/v1/models` returned `Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf`.
- localhost:8080 `/v1/chat/completions` advisory review of the AUIR-3 diff and test returned `verdict: pass` with no concerns. This is advisory evidence only.
Atlas UI evidence:
- In-app Browser minimal Atlas harness loaded `web/js/atlas_pipeline_api.js` and `web/js/atlas_claude_panel.js`, seeded reload hints, auto-activated Atlas, and observed `/api/atlas/pipeline/events/pool_auir3/run_auir3?workspace_id=default&after_sequence=0`.
- The same browser run showed the Atlas shell visible, token total restored to `42`, tps restored to `3.5`, and the transcript showing `patch_generation  ·  tokens 42 / 8192`.
Reload/resume evidence:
- Contract tests assert activation/project restore calls replay, replay consumes `progress_events`/`latest_progress`, local run/sequence hints are used, and restored progress dispatches `atlas:llm-progress`.
- Browser minimal harness verified replay after a simulated reload from local storage hints.
Project Intelligence evidence:
- Not applicable to AUIR-3.
Impact analysis evidence:
- Not applicable to AUIR-3.
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- Portal runtime paths were not changed.
Unavailable checks:
- `python scripts\smoke_ui_modes_playwright.py --only atlas_current_ui_smoke` failed before AUIR-3-specific restoration because the current mock-backed full `ui.html` smoke hit pre-existing page errors: `switchTab is not defined` and `_echoRefreshStatusLine is not defined`. This is recorded as failed/unavailable evidence, not a pass.
- No live approved Atlas development run was executed through the full browser UI in this package.
Safety invariants:
- Proposal / Safe Apply / Verification boundaries were not bypassed.
- Restored UI state is derived from server replay/latest progress plus local identity hints; UI rendering is not treated as runtime evidence.
- No external provider was enabled by default.
- No secrets or generated data persistence paths were added.
- `unavailable` checks are not marked as passed.
Remaining gaps:
- Live indicator reconnecting/stale/stalled visual distinctions remain AUIR-4.
- Full `ui.html` Playwright smoke needs a separate harness/static-serving fix before it can be authoritative UI evidence.
Next package: AUIR-4 Live indicator reconnection and stale/stalled state UX
Blocker: none
```

```text
Completed package: AUIR-4 Live indicator reconnection and stale/stalled state UX
Status: completed
Changed modules/files:
- web/js/atlas_claude_panel.js
- web/css/app.css
- ui.html
- tests/test_atlas_runtime_progress_connection_state_contract.py
- tests/test_atlas_runtime_status_panel_contract.py
- tests/test_atlas_dashboard_ui_contract.py
- docs/atlas_runtime_progress_resume_hardening_current_status.md
Behavior implemented:
- Added a shared runtime progress connection-state classifier for `live`, `reconnecting`, `stale`, `stalled`, `terminal`, and `unknown`.
- Updated the LLM progress line to expose `dataset.connectionState`, distinct state classes, state labels, last-progress age, and backend stalled reasons.
- Updated runtime status panel rendering to expose `data-atlas-runtime-connection-state`, distinct runtime classes, and non-empty state rows for reconnecting/stale/stalled/terminal/unknown states.
- Rendered `reconnecting` while server progress replay is being fetched, `unknown` when replay returns no events, and `stale` when replay fails but the latest runtime snapshot is still available.
- Kept backend-stalled progress visually distinct from disconnected/stale UI by requiring explicit stalled status/event/reason for the `stalled` state.
- Prevented empty latest autopilot result payloads from overwriting a meaningful replay/restored runtime panel.
- Added CSS classes for distinct progress/runtime state styling and bumped cache-bust versions for `app.css` and `atlas_claude_panel.js`.
Focused tests:
- `python -m pytest tests\test_atlas_runtime_progress_connection_state_contract.py tests\test_atlas_reload_resume_progress_ui_contract.py tests\test_atlas_dev_phase_llm_progress_indicator_contract.py tests\test_atlas_runtime_status_panel_contract.py tests\test_atlas_dashboard_ui_contract.py -q` -> 75 passed.
Syntax checks:
- `python scripts\check_ui_inline_script_syntax.py` -> passed for 1 inline script block and 16 external script files.
- `git diff --check` -> passed; only Git line-ending warnings for existing Windows checkout behavior.
Affected tests:
- `python -m pytest tests\test_static_js_serving.py tests\test_ui_js_dependency_contract.py tests\test_atlas_dashboard_ui_contract.py -q` -> 64 passed.
Real model evidence:
- localhost:8080 `/v1/models` returned `Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf`.
- localhost:8080 `/v1/chat/completions` advisory review of the final AUIR-4 diff returned `verdict: pass` with no concerns. This is advisory evidence only.
Atlas UI evidence:
- In-app Browser minimal Atlas harness loaded the real `atlas_pipeline_api.js`, `atlas_claude_panel.js`, and `app.css`.
- The harness showed a visible `reconnecting` runtime panel while `/api/atlas/pipeline/events/pool_auir4/run_auir4?...after_sequence=0` was delayed.
- After a backend `llm_stalled_after_progress` event, the browser showed `lineState=stalled`, text `patch_generation  ·  stalled: backend heartbeat stopped  ·  tokens 12 / 8192`, `panelState=stalled`, and token total `12`.
Reload/resume evidence:
- The browser harness seeded reload hints in localStorage, reloaded into Atlas, and replayed server progress with `after_sequence=0`.
- Contract tests assert replay-visible states and non-empty reconnect/stale/stalled panels.
Project Intelligence evidence:
- Not applicable to AUIR-4.
Impact analysis evidence:
- Not applicable to AUIR-4.
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- Portal runtime paths were not changed.
Unavailable checks:
- No full live approved Atlas development run was executed through the complete `ui.html` surface in this package.
- Full mock-backed `ui.html` Playwright smoke remains unavailable as authoritative evidence until the existing static-serving/startup-order issue from AUIR-3 is fixed or worked around in AUIR-5.
Safety invariants:
- Proposal / Safe Apply / Verification boundaries were not bypassed.
- UI rendering and browser harness observations are recorded as UI evidence, not runtime authority.
- Backend stalled state is not inferred from UI age alone; explicit backend stalled status/event/reason is required.
- No external provider was enabled by default.
- No secrets or generated data persistence paths were added.
- `unavailable` checks are not marked as passed.
Remaining gaps:
- AUIR-5 must consolidate regression coverage and produce mobile/browser reload smoke evidence or truthfully record remaining smoke blockers.
Next package: AUIR-5 Regression tests and mobile/browser reload smoke
Blocker: none
```

```text
Completed package: AUIR-5 Regression tests and mobile/browser reload smoke
Status: completed
Changed modules/files:
- scripts/smoke_ui_modes_playwright.py
- tests/test_phase25_4_1_playwright_http_smoke_harness_contract.py
- ui.html
- docs/atlas_runtime_progress_resume_hardening_current_status.md
Behavior implemented:
- Updated the mock-backed Playwright smoke server to serve `/static/*` from `web/` and `/assets/*` from `assets/` with path escape checks, no-store responses, and content types.
- Removed an early unused `switchTab` reference in `ui.html` that could throw before `web/js/panels.js` initialized the function.
- Aligned `atlas_current_ui_smoke` with the current Atlas Claude shell by using `#atlas-claude-col`, submitting through `#atlas-claude-input` / `#atlas-claude-send-btn`, and verifying visible `PlanPool 作成` output.
- Added deterministic mock runtime/progress replay routes for `pool_auir5_reload` / `run_auir5_reload`.
- Added `atlas_reload_resume_progress_smoke`, which seeds Atlas pool/run/sequence hints, reloads the full `ui.html`, activates Atlas, and verifies a restored live LLM indicator plus runtime panel state from server replay.
- Aligned `mobile_mode_switches` with the current Atlas Claude shell and treated absent optional mobile panels as hidden instead of failing `getComputedStyle` on missing elements.
Focused tests:
- `python -m pytest tests\test_phase25_4_1_playwright_http_smoke_harness_contract.py tests\test_static_js_serving.py tests\test_ui_js_dependency_contract.py -q` -> 21 passed.
Syntax checks:
- `python -m py_compile scripts\smoke_ui_modes_playwright.py` -> passed.
- `python scripts\check_ui_inline_script_syntax.py` -> passed for 1 inline script block and 16 external script files.
- `git diff --check` -> passed; only Git line-ending warnings for existing Windows checkout behavior.
Affected tests:
- Static JS serving and UI dependency contract tests were included in the focused test run.
Real model evidence:
- localhost:8080 `/v1/models` returned `Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf`.
- localhost:8080 `/v1/chat/completions` advisory review of the final AUIR-5 diff returned `verdict: pass` with no blockers. This is advisory evidence only.
Atlas UI evidence:
- `python scripts\smoke_ui_modes_playwright.py --only atlas_current_ui_smoke` -> 1 pass, 0 fail.
- `python scripts\smoke_ui_modes_playwright.py --only atlas_reload_resume_progress_smoke` -> 1 pass, 0 fail.
- `python scripts\smoke_ui_modes_playwright.py --only mobile_mode_switches` -> 2 pass, 0 fail.
Reload/resume evidence:
- Full mock-backed browser reload smoke restored Atlas from local pool/run/sequence hints after `page.reload()`.
- The restored UI showed `#atlas-llm-progress-line` with `data-connection-state="live"` and text containing `patch_generation` and `tokens 64 / 8192`.
- The restored runtime panel for `pool_auir5_reload` showed `data-atlas-runtime-connection-state="live"` and `復元: server progress replay restored`.
Project Intelligence evidence:
- Not applicable to AUIR-5.
Impact analysis evidence:
- Not applicable to AUIR-5.
Web research evidence:
- Not applicable; external/web calls remain disabled by default.
Runtime/Portal evidence:
- Portal runtime paths were not changed.
Unavailable checks:
- No full live approved Atlas development run was executed through the complete browser UI in this package.
- Mock-backed browser smoke evidence is UI evidence, not live runtime authority.
Safety invariants:
- Proposal / Safe Apply / Verification boundaries were not bypassed.
- No approval, execution, patch apply, bulk apply, or external-code exposure default was enabled by the smoke harness.
- UI rendering and browser smoke observations are recorded as UI evidence, not runtime evidence.
- No external provider was enabled by default.
- No secrets or generated data persistence paths were added.
- `unavailable` checks are not marked as passed.
Remaining gaps:
- AUIR runtime progress/resume hardening is complete enough to return to PIBIH-1.
- Live approved Atlas development runtime evidence remains a future end-to-end check, not an AUIR-5 mock-smoke pass.
Next package: AUIR-6 Return to PIBIH-1 LLM planning timeout hardening
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
