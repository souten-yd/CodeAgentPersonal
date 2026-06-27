# Atlas Project Restore / Visual Contract Recovery Plan

> Active recovery track after CS9-CS16.
>
> Goal: fix the two production regressions observed on mobile Atlas: a newly-created project can show a PlanPool from another project, and an HTML Rubik-cube style task can fail verification because the visual contract incorrectly requires canvas evidence.

## Problem statement

Observed UI symptoms:

1. A new Atlas project was created, but Atlas re-rendered a plan from another project.
2. The shown run failed with:

```text
visual_contract_failed
missing=canvas_exists
browser_smoke_failed:canvas_frame_not_detected:no_frame_change
```

The user request was:

```text
ルービックキューブを解くプログラムをHTMLで作って。初期状態はランダムで、ボタンを押すと自動で順次操作されて色が全面揃うようにして。
```

That request does not require `<canvas>`. A DOM/CSS/SVG HTML implementation with a button, visible cube state, step-by-step operation, and final solved state should be valid.

## Recovery track name

Use **RV0-RV8** for this recovery track.

```text
RV = Restore / Visual recovery
```

## Root-cause hypothesis to verify first

### A. Project restore cross-contamination

Current code has global client-side recovery hints:

```text
atlas_claude_last_pool_id
atlas_claude_last_run_id
atlas_claude_last_event_sequence
```

These keys are not scoped by project name or workspace id. `activate()` can fall back to the global last pool when `projectName()` is empty. Project picker bootstrap can set the active project without immediately calling `AtlasClaudePanel.loadProject(project.name)`. This creates a startup race where an old global pool is rendered before the newly selected project is loaded.

### B. Visual contract over-requires canvas

The visual pipeline selects a contract through:

```text
VisualRequirementNormalizer -> VisualTaskClassifier -> VisualContractRegistry
```

Canvas contracts require `canvas_exists` and frame changes. For the Rubik HTML solver task, expected classification should be `interactive_web_app` or `ui_component`, not `canvas_animation` or `canvas_game`, unless the user explicitly asks for canvas/WebGL/game canvas.

### C. Stale visual failure may be a secondary symptom

Because a different project's old PlanPool can be restored, the canvas failure may be from a stale pool rather than the new Rubik project. Fix project restore isolation first, then verify the Rubik classification and visual contract independently.

## Non-negotiable rules

- No path may bypass Proposal / Safe Apply / Verification.
- UI rendering is not runtime evidence.
- Mock output is not live evidence.
- `unavailable` is not `passed`.
- Backend Run control remains authoritative.
- Web UI and CLI must not directly orchestrate patch generation, patch approval, Safe Apply, Verification, or multi-item autopilot execution.
- Project restore must be project/workspace-scoped. A global hint must never resurrect a pool into a different active project.
- A new project with no active PlanPool must show an empty prompt, not the last global PlanPool.
- Visual contract selection must not require canvas unless the requirement explicitly needs canvas/WebGL/game-canvas behavior or the generated artifact actually declares a canvas contract intentionally.
- Runtime smoke may provide stronger evidence than static heuristics, but it must not convert unknown/unavailable into passed.

## Files to inspect before editing

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
tests/test_atlas_inflight_resume_recovery_contract.py
tests/test_atlas_runtime_status_panel_contract.py
tests/test_atlas_auto_verification_service.py
tests/test_atlas_visual_contract_registry.py
tests/test_visual_contract_matrix.py
```

## Target behavior

### Project restore

```text
Project A has pool A.
Project B is newly created and has no pool.
Opening Atlas on Project B must show an empty prompt.
It must not render pool A, run A, events A, stage block A, or visual failure A.
```

Allowed behavior:

- If Project B has its own `active_pool_id` in server conversation meta, restore B's pool.
- If Project B has no conversation meta but backend continuation latest for workspace B returns a pool, restore that B-scoped pool.
- If Project B has no pool, clear project-local plan UI and show the empty prompt.
- Legacy global localStorage hints may be migrated or ignored, but they must not override active project identity.

### Visual contract

For the Rubik HTML solver task:

```text
artifact_type: interactive_web_app or ui_component
contract_id: interactive_web_app_visual_v1 or ui_component_visual_v1
required signals: page_loads + controls/state change, not canvas_exists
```

The verifier should accept a DOM/CSS/SVG implementation when it has:

- visible cube representation;
- randomized initial state or deterministic randomizable state;
- solve/start button;
- state changes after the button is clicked;
- final solved visual state;
- no hard JS errors.

## Work packages

### RV0: Baseline proof and reproduction tests

Goal: freeze the two regressions with failing tests before changing behavior.

Tasks:

1. Add a UI/static contract test proving `activate()` currently has a global last-pool fallback when no project is ready.
2. Add a project bootstrap contract test proving `bootstrapProjects()` sets an active project and must call panel `loadProject()` for that selected project.
3. Add a restore isolation test for the intended behavior: selected project B with no pool must not restore project A's global pool.
4. Add a visual classification test for the Rubik HTML solver request.
5. Add a visual verifier test proving Rubik HTML solver must not require `canvas_exists` unless the text explicitly says canvas/WebGL.

Acceptance:

- At least one new test fails on the current code or clearly asserts a missing contract.
- Tests name the regression directly: `project_restore_cross_contamination` and `rubik_solver_canvas_overrequirement`.
- No production behavior changes in RV0.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_project_restore_isolation.py
python -m pytest -q tests/test_atlas_visual_rubik_contract.py
```

### RV1: Project-scoped client recovery keys

Goal: remove global localStorage cross-contamination for pool/run/event hints.

Tasks:

1. Add helper functions in `web/js/atlas_claude_panel.js`:

```text
projectScopedStorageKey(baseKey, wsId)
setProjectScopedHint(baseKey, value)
getProjectScopedHint(baseKey)
removeProjectScopedHints()
```

2. Scope these hints by `workspaceId()` or project name:

```text
atlas_claude:<workspace_id>:last_pool_id
atlas_claude:<workspace_id>:last_run_id
atlas_claude:<workspace_id>:last_event_sequence
```

3. Keep read-only migration from the old global keys only when there is no active project and no project picker available. Do not migrate global keys into an active project automatically.
4. Replace direct uses of `localStorage.setItem(STORAGE_LAST_POOL_ID_KEY, ...)` and `getItem(STORAGE_LAST_RUN_ID_KEY)` in restore/progress paths with scoped helpers.
5. On `loadProject(name)`, clear visible plan/stage/progress nodes before rendering that project's state.

Acceptance:

- A pool restored in Project A is not visible after selecting Project B.
- Global `atlas_claude_last_pool_id` is ignored when `projectName()` exists.
- Existing reload/resume for the same project still works.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_project_restore_isolation.py
python -m pytest -q tests/test_atlas_inflight_resume_recovery_contract.py
node --check web/js/atlas_claude_panel.js
```

### RV2: Bootstrap order and selected-project load

Goal: ensure the panel always loads the selected project after project picker bootstrap.

Tasks:

1. Update `web/js/app.js` `bootstrapProjects()` so that after `setActiveProject(chosen)` it calls:

```text
root.AtlasClaudePanel?.loadProject?.(chosen.name)
```

only when the panel is present and the selected name is non-empty.

2. For `createProject(name)`, after creation and selection, ensure the new project is loaded even if the panel had already activated.
3. Add idempotence guard so repeated bootstrap does not append duplicate empty prompts or duplicate plan cards.
4. Ensure `selectProject()` still calls `loadProject()` as it already does.

Acceptance:

- Initial page load with stored/new project renders that project only.
- New project creation immediately clears old plan UI and shows the new project's empty prompt.
- No duplicate `指示を入力してください` messages on repeated activation.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_project_picker_bootstrap_contract.py
node --check web/js/app.js
```

### RV3: Backend continuation/recovery workspace isolation audit

Goal: verify server-side latest/recovery endpoints are truly workspace-scoped.

Tasks:

1. Inspect `_atlas_components(request, workspace_id=...)`, `AtlasJournal`, and `AtlasRecoveryService.recover_latest()`.
2. Add tests that create two workspaces/journals and confirm:
   - `/api/atlas/continuation/latest?workspace_id=A` returns A only;
   - `/api/atlas/continuation/latest?workspace_id=B` returns B only;
   - no fallback to default when workspace_id is specified.
3. If any server function falls back to default workspace after a missing workspace, change it to return `no_workspace` / `no_plan_pool` for that workspace.
4. Verify `workspace_id` is passed by UI calls to `getContinuationLatest`, `getContinuationPool`, `getPlanRuntimeStatus`, and event replay.

Acceptance:

- Backend tests prove no cross-workspace latest pool leakage.
- Missing workspace returns empty/no_plan_pool, not another workspace's pool.
- UI calls include workspace_id for all project restore requests.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_continuation_workspace_isolation.py
python -m pytest -q tests/test_atlas_api_pipeline.py
```

### RV4: Rubik / cube visual classification fix

Goal: classify HTML Rubik solver as interactive web app unless canvas/WebGL is explicit.

Tasks:

1. Add deterministic tests for Japanese and English variants:

```text
ルービックキューブを解くプログラムをHTMLで作って。初期状態はランダムで、ボタンを押すと自動で順次操作されて色が全面揃うようにして。
Create an HTML Rubik cube solver with a random initial state and a button that solves it step by step.
```

Expected:

```text
artifact_type in {interactive_web_app, ui_component}
runtime_requirements includes browser_required and input_required
runtime_requirements does not include canvas_required unless explicit canvas/webgl exists
```

2. Update keyword rules if needed:
   - `cube`, `Rubik`, `solver`, `HTML`, `button`, `state`, `solve` should imply interactive web app, not canvas.
   - `game` should not be inferred from cube/solver alone.
   - `canvas_required` should require explicit canvas/WebGL/game-canvas keywords.
3. If Japanese terms are not detected, add minimal Japanese keyword support for this case:
   - `ルービック`, `キューブ`, `ボタン`, `自動`, `順次`, `揃う`, `解く`, `HTML`.
4. Do not broaden game detection in a way that makes business apps or UI widgets become games.

Acceptance:

- Rubik HTML solver selects non-canvas visual contract.
- Explicit `canvasでルービックキューブを描画` still selects canvas animation or canvas app.
- Existing canvas/game tests still pass.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_visual_rubik_contract.py
python -m pytest -q tests/test_atlas_visual_task_classifier.py
python -m pytest -q tests/test_visual_contract_matrix.py
```

### RV5: Visual verifier contract evidence and UI diagnostics

Goal: make future visual failures explain why a contract was selected.

Tasks:

1. Ensure verification metadata persists:
   - `visual_contract_id`
   - `artifact_type`
   - `visual_intent`
   - `classification_context`
   - `normalized_requirement.source_phrases`
   - `required_signals`
   - `missing_signals`
2. Update UI failure summary rendering to include compact diagnostics when available:

```text
visual_contract=<id>
artifact_type=<type>
missing=<signals>
classification_context=<first 160 chars>
```

3. Keep mobile output compact; do not flood the main card.
4. Add tests that a canvas failure summary includes the contract id and classification context.

Acceptance:

- When `canvas_exists` is missing, the user can see which contract required it.
- Rubik DOM solver failures do not mention `canvas_exists` unless explicit canvas was requested.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_visual_failure_diagnostics.py
python -m pytest -q tests/test_atlas_runtime_status_panel_contract.py
```

### RV6: End-to-end project isolation scenario

Goal: validate the exact user scenario.

Scenario:

1. Create Project A.
2. Create/run any plan that leaves a visible stage block/failure.
3. Create Project B.
4. Open Atlas on Project B.
5. Assert Project B shows no Project A pool, no Project A stage block, and no Project A failure.
6. Submit Rubik HTML solver request in Project B.
7. Assert generated PlanPool and Run belong to Project B workspace only.

Acceptance:

- No cross-project plan display.
- No cross-project run events.
- No global localStorage fallback in active project mode.

Suggested tests:

```text
python -m pytest -q tests/test_atlas_project_restore_e2e_contract.py
```

### RV7: Live 8080 Rubik validation

Goal: validate the user-visible flow with the weak local model.

Use:

```text
http://127.0.0.1:8080/v1
```

Required live checks:

1. `GET /v1/models` succeeds.
2. New project created.
3. Rubik HTML solver goal creates a PlanPool in the new project's workspace.
4. Backend Run API executes; UI/CLI only watch.
5. Verification does not fail for `missing=canvas_exists` unless implementation explicitly chose canvas and has broken canvas evidence.
6. If Playwright/browser is unavailable, mark browser smoke blocked/skipped truthfully, not passed.

Acceptance:

- Live result JSON records project name, workspace_id, pool_id, run_id, visual_contract_id, artifact_type, status, warnings.
- `canvas_exists` is absent from hard missing signals for non-canvas Rubik implementation.
- If live model is unavailable, status is `blocked_live_llm_unavailable`, not passed.

Suggested runner:

```text
tools/run_atlas_restore_visual_recovery_eval.py
```

### RV8: Final review and docs closeout

Goal: close the recovery with deterministic evidence and advisory LLM review.

Tasks:

1. Add final review mode to `tools/run_atlas_restore_visual_recovery_eval.py`.
2. Evidence bundle must include:
   - focused test output;
   - project isolation fixture result;
   - localStorage scoped-key assertion;
   - backend workspace isolation result;
   - Rubik classification result;
   - visual contract result;
   - live 8080 result or truthful block;
   - UI screenshot note if manually verified.
3. Ask 8080 LLM to review evidence only after deterministic tests pass.
4. Update this plan status table.
5. Update `AGENTS.md`, `Agent.md`, and `docs/AGENTS.md` to mark RV0-RV8 completed or state the next active track.

Acceptance:

- All RV0-RV7 checks passed or truthfully blocked.
- Final report written.
- Agent entrypoints no longer say CS9-CS16 is the only current active task.

## Status

| Package | Goal | Status | Evidence |
|---|---|---|---|
| RV0 | Baseline proof and reproduction tests | completed | `tests/test_atlas_project_restore_isolation.py`; `tests/test_atlas_project_picker_bootstrap_contract.py`; `tests/test_atlas_visual_rubik_contract.py`; focused 10 passed / 5 xfailed |
| RV1 | Project-scoped client recovery keys | completed | `web/js/atlas_claude_panel.js`; focused 17 passed; project picker RV2 contract remains xfailed |
| RV2 | Bootstrap order and selected-project load | completed | `web/js/app.js`; focused/affected 21 passed |
| RV3 | Backend continuation/recovery workspace isolation audit | completed | `tests/test_atlas_continuation_workspace_isolation.py`; focused/affected 37 passed |
| RV4 | Rubik / cube visual classification fix | completed | `agent/atlas_visual_task_classifier.py`; Rubik focused/affected 74 passed |
| RV5 | Visual verifier contract evidence and UI diagnostics | completed | `tests/test_atlas_visual_failure_diagnostics.py`; focused/affected 9 passed + 71 passed |
| RV6 | End-to-end project isolation scenario | completed | `tests/test_atlas_project_restore_e2e_contract.py`; focused/affected 15 passed + 9 passed |
| RV7 | Live 8080 Rubik validation | blocked | `tools/run_atlas_restore_visual_recovery_eval.py`; live 8080 run blocked by patch generation failure |
| RV8 | Final review and docs closeout | completed | `--final-review` evidence bundle; 8080 advisory review passed |

## Completion evidence

### RV0 — Baseline proof and reproduction tests (completed 2026-06-26)

Status: completed; PR #2100 merged

Changed files:

- `tests/test_atlas_project_restore_isolation.py`
- `tests/test_atlas_project_picker_bootstrap_contract.py`
- `tests/test_atlas_visual_rubik_contract.py`
- `tests/test_atlas_visual_contract_registry.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Validation:

- `python -m pytest -q tests\test_atlas_project_restore_isolation.py tests\test_atlas_project_picker_bootstrap_contract.py tests\test_atlas_visual_rubik_contract.py` -> 10 passed, 5 xfailed
- `python -m pytest -q tests\test_atlas_inflight_resume_recovery_contract.py tests\test_atlas_runtime_status_panel_contract.py` -> 11 passed
- `python -m pytest -q tests\test_atlas_visual_task_classifier.py tests\test_atlas_visual_contract_registry.py tests\test_visual_contract_matrix.py` -> 86 passed
- `python -m py_compile tests\test_atlas_project_restore_isolation.py tests\test_atlas_project_picker_bootstrap_contract.py tests\test_atlas_visual_rubik_contract.py tests\test_atlas_visual_contract_registry.py` -> passed
- `node --check web\js\atlas_claude_panel.js` -> passed
- `node --check web\js\app.js` -> passed
- `git diff --check` -> passed with CRLF warning only for `tests/test_atlas_visual_contract_registry.py`

Baseline proof captured:

- Project restore still has unscoped browser recovery keys: `atlas_claude_last_pool_id`, `atlas_claude_last_run_id`, and `atlas_claude_last_event_sequence`.
- `activate()` still has a no-project global last-pool fallback that can render and restore a globally remembered pool.
- Runtime progress replay still writes pool/run/event hints to global localStorage keys.
- `bootstrapProjects()` sets the chosen active project and renders the picker, but does not yet call `AtlasClaudePanel.loadProject(chosen.name)`.
- Rubik HTML solver requests do not explicitly require canvas, and a wrong canvas contract reproduces `missing=canvas_exists`.
- Expected RV1/RV2/RV4 behavior is captured as strict `xfail` tests: scoped recovery helpers, bootstrap selected-project load, Rubik interactive classification, and explicit Japanese canvas wording.

Behavior implemented: tests and documentation only; no production behavior changed.

Safety invariants: no Proposal / Safe Apply / Verification path changed; unavailable evidence is not converted into passed; UI and CLI execution authority boundaries are unchanged.

Remaining gaps: RV1 project-scoped client recovery keys, RV2 bootstrap selected-project load, RV3 backend workspace isolation audit, RV4 Rubik classification fix, RV5 diagnostics, RV6 exact project isolation scenario, RV7 live 8080 validation, RV8 final review.

Next package: RV1 — Project-scoped client recovery keys

Blocker: none

Proof level: `baseline_restore_visual_regressions_captured`

### RV1 — Project-scoped client recovery keys (completed 2026-06-26)

Status: completed; PR #2101 merged

Changed files:

- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_project_restore_isolation.py`
- `tests/test_atlas_inflight_resume_recovery_contract.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Validation:

- `python -m pytest -q tests\test_atlas_project_restore_isolation.py tests\test_atlas_inflight_resume_recovery_contract.py tests\test_atlas_runtime_status_panel_contract.py` -> 17 passed
- `python -m pytest -q tests\test_atlas_project_picker_bootstrap_contract.py` -> 3 passed, 1 xfailed
- `python -m py_compile tests\test_atlas_project_restore_isolation.py tests\test_atlas_inflight_resume_recovery_contract.py` -> passed
- `node --check web\js\atlas_claude_panel.js` -> passed
- `git diff --check` -> passed with CRLF warnings only

Behavior implemented: added `projectScopedStorageKey()`, `setProjectScopedHint()`, `getProjectScopedHint()`, and `removeProjectScopedHints()` in `web/js/atlas_claude_panel.js`. Pool/run/event recovery hints now use `atlas_claude:<workspace_id>:last_pool_id`, `atlas_claude:<workspace_id>:last_run_id`, and `atlas_claude:<workspace_id>:last_event_sequence` whenever an active project/workspace exists.

Legacy behavior: old global keys remain read-only fallback only when no active project scope exists. Active projects no longer write or read direct global pool/run/event hint keys. A selected project with no pool clears only its scoped hints and renders the empty prompt.

Safety invariants: no backend Run control, Proposal, Safe Apply, Verification, retry, item order, or terminal status behavior changed. UI remains a client of backend state; unavailable evidence is not converted into passed.

Remaining gaps: RV2 bootstrap selected-project load, RV3 backend workspace isolation audit, RV4 Rubik classification fix, RV5 diagnostics, RV6 exact project isolation scenario, RV7 live 8080 validation, RV8 final review.

Next package: RV2 — Bootstrap order and selected-project load

Blocker: none

Proof level: `project_scoped_client_recovery_keys_complete`

### RV2 — Bootstrap order and selected-project load (completed 2026-06-26)

Status: completed; PR #2102 merged

Changed files:

- `web/js/app.js`
- `tests/test_atlas_project_picker_bootstrap_contract.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Validation:

- `python -m pytest -q tests\test_atlas_project_picker_bootstrap_contract.py tests\test_atlas_project_restore_isolation.py tests\test_atlas_inflight_resume_recovery_contract.py tests\test_atlas_runtime_status_panel_contract.py` -> 21 passed
- `python -m py_compile tests\test_atlas_project_picker_bootstrap_contract.py` -> passed
- `node --check web\js\app.js` -> passed
- `node --check web\js\atlas_claude_panel.js` -> passed
- `git diff --check` -> passed with CRLF warnings only

Behavior implemented: `bootstrapProjects()` now calls `AtlasClaudePanel.loadProject(chosen.name)` immediately after `setActiveProject(chosen)` and picker rendering when the selected project name is available. Project creation and explicit selection continue to route through `selectProject()`, which already loads the selected project.

Safety invariants: browser bootstrap now loads the active project into the Atlas panel but does not start execution, patch generation, Safe Apply, Verification, retry, or autopilot. Backend Run control remains authoritative.

Remaining gaps: RV3 backend workspace isolation audit, RV4 Rubik classification fix, RV5 diagnostics, RV6 exact project isolation scenario, RV7 live 8080 validation, RV8 final review.

Next package: RV3 — Backend continuation/recovery workspace isolation audit

Blocker: none

Proof level: `bootstrap_selected_project_load_complete`

### RV3 — Backend continuation/recovery workspace isolation audit (completed 2026-06-26)

Status: completed; PR #2103 merged

Changed files:

- `tests/test_atlas_continuation_workspace_isolation.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Validation:

- `python -m pytest -q tests\test_atlas_continuation_workspace_isolation.py tests\test_atlas_api_pipeline.py` -> 37 passed
- `python -m pytest -q tests\test_atlas_project_restore_isolation.py tests\test_atlas_project_picker_bootstrap_contract.py tests\test_atlas_inflight_resume_recovery_contract.py` -> 15 passed
- `python -m py_compile tests\test_atlas_continuation_workspace_isolation.py` -> passed
- `node --check web\js\atlas_pipeline_api.js` -> passed
- `git diff --check` -> passed

Behavior implemented: tests and documentation only; no production behavior changed. Existing backend continuation/recovery components already use `AtlasJournal(root, workspace_id=...)`, and missing explicit workspaces return `no_workspace` instead of falling back to `default`.

Isolation proof: API tests create separate default/project A/project B workspaces and verify `/api/atlas/continuation/latest`, `/api/atlas/recovery/latest`, and UI client restore calls stay scoped by `workspace_id`. Missing workspace requests return empty pool/run ids with `no_workspace`.

Safety invariants: recovery and continuation remain read-only; no Proposal, Safe Apply, Verification, backend run execution, retry, or UI orchestration behavior changed.

Remaining gaps: RV4 Rubik classification fix, RV5 diagnostics, RV6 exact project isolation scenario, RV7 live 8080 validation, RV8 final review.

Next package: RV4 — Rubik / cube visual classification fix

Blocker: none

Proof level: `backend_continuation_workspace_isolation_verified`

### RV4 — Rubik / cube visual classification fix (completed 2026-06-26)

Status: completed; PR #2104 merged

Changed files:

- `agent/atlas_visual_requirement_normalizer.py`
- `agent/atlas_visual_task_classifier.py`
- `tests/test_atlas_visual_rubik_contract.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Validation:

- `python -m pytest -q tests\test_atlas_visual_rubik_contract.py tests\test_atlas_visual_task_classifier.py tests\test_visual_contract_matrix.py` -> 74 passed
- `python -m pytest -q tests\test_atlas_visual_contract_registry.py tests\test_atlas_auto_verification_service.py` -> 35 passed
- `python -m pytest -q tests\test_atlas_project_restore_isolation.py tests\test_atlas_project_picker_bootstrap_contract.py` -> 10 passed
- `python -m py_compile agent\atlas_visual_requirement_normalizer.py agent\atlas_visual_task_classifier.py tests\test_atlas_visual_rubik_contract.py` -> passed
- `git diff --check` -> passed with CRLF warnings only

Behavior implemented: Rubik/cube HTML solver requests with button/solve interaction now classify as `interactive_web_app` with `browser_required` and `input_required`, without `canvas_required`. Explicit canvas wording, including Japanese `canvasでルービックキューブを描画`, still selects a canvas contract and requires `canvas_exists`.

Keyword updates: added minimal Japanese support for `ボタン`, `押す`, `ルービック`, `キューブ`, `解く`, `揃う`, `そろう`, `自動`, `順次`, `初期状態`, and `ランダム`; made `HTML` adjacent to Japanese text detectable without requiring word boundaries.

Safety invariants: visual classification remains deterministic and generic; no game-only special case was added. Canvas remains required only for explicit canvas/WebGL/canvas-rendering requests. No Proposal, Safe Apply, Verification, or Run control authority changed.

Remaining gaps: RV5 diagnostics, RV6 exact project isolation scenario, RV7 live 8080 validation, RV8 final review.

Next package: RV5 — Visual verifier contract evidence and UI diagnostics

Blocker: none

Proof level: `rubik_html_solver_non_canvas_classification_complete`

### RV5 — Visual verifier contract evidence and UI diagnostics (completed 2026-06-26)

Status: completed; PR #2105 merged

Changed files:

- `agent/atlas_auto_verification_service.py`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_visual_failure_diagnostics.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Validation:

- `python -m pytest -q tests\test_atlas_visual_failure_diagnostics.py tests\test_atlas_runtime_status_panel_contract.py` -> 9 passed
- `python -m pytest -q tests\test_atlas_visual_rubik_contract.py tests\test_visual_contract_matrix.py tests\test_atlas_auto_verification_service.py` -> 71 passed
- `python -m py_compile agent\atlas_auto_verification_service.py tests\test_atlas_visual_failure_diagnostics.py` -> passed
- `node --check web\js\atlas_claude_panel.js` -> passed
- `git diff --check` -> passed with CRLF warnings only

Behavior implemented: visual verification metadata now records compact contract diagnostics in `visual_contract`: `contract_id`, `artifact_type`, `visual_intent`, `classification_context`, `source_phrases`, `required_signals`, and `missing_signals`. Pool-level `visual_pipeline` metadata also records required signals, classification context, and normalized source phrases.

UI diagnostics: visual failure summaries now include `visual_contract=<id>`, `artifact_type=<type>`, `required=<signals>`, `missing=<signals>`, and `classification_context=<first 160 chars>` when available, plus browser-smoke status and existing repair guidance.

Safety invariants: diagnostics are read-only observability. They do not change classification, verification pass/fail semantics, Proposal, Safe Apply, backend Run control, retry, or UI execution authority.

Remaining gaps: RV6 exact project isolation scenario, RV7 live 8080 validation, RV8 final review.

Next package: RV6 — End-to-end project isolation scenario

Blocker: none

Proof level: `visual_contract_diagnostics_complete`

### RV6 — End-to-end project isolation scenario (completed 2026-06-26)

Status: completed; PR #2106 merged

Changed files:

- `tests/test_atlas_project_restore_e2e_contract.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Validation:

- `python -m pytest -q tests\test_atlas_project_restore_e2e_contract.py` -> 2 passed
- `python -m pytest -q tests\test_atlas_project_restore_e2e_contract.py tests\test_atlas_project_restore_isolation.py tests\test_atlas_project_picker_bootstrap_contract.py tests\test_atlas_continuation_workspace_isolation.py` -> 15 passed
- `python -m pytest -q tests\test_atlas_visual_rubik_contract.py tests\test_atlas_visual_failure_diagnostics.py` -> 9 passed
- `python -m py_compile tests\test_atlas_project_restore_e2e_contract.py` -> passed
- `node --check web\js\atlas_claude_panel.js` -> passed

Scenario covered: Project A creates and dry-runs a PlanPool, persists its active pool/run meta, then Project B is created and opened with no pool. Project B's conversation meta, continuation latest, and recovery latest remain empty and scoped to B. After submitting the Rubik HTML solver request in Project B, the generated PlanPool, dry-run, continuation latest, and recovery latest belong to Project B while Project A still resolves only to Project A's pool/run.

Safety invariants: RV6 adds proof only. It does not change Proposal, Safe Apply, Verification, backend Run control, retry, client execution authority, or visual verification semantics. Active project mode continues to avoid global localStorage restoration.

Remaining gaps: RV7 live 8080 Rubik validation, RV8 final review.

Next package: RV7 — Live 8080 Rubik validation

Blocker: none

Proof level: `project_restore_e2e_isolation_complete`

### RV7 — Live 8080 Rubik validation (blocked 2026-06-26)

Status: blocked by live 8080 patch generation; PR #2107 merged

Changed files:

- `tools/run_atlas_restore_visual_recovery_eval.py`
- `tests/test_atlas_restore_visual_recovery_eval.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Validation:

- `python -m pytest -q tests\test_atlas_restore_visual_recovery_eval.py` -> 5 passed
- `python -m py_compile tools\run_atlas_restore_visual_recovery_eval.py tests\test_atlas_restore_visual_recovery_eval.py` -> passed
- `python tools\run_atlas_restore_visual_recovery_eval.py --output-json ca_data\atlas_restore_visual_recovery_eval\rv7_live_8080.json --timeout-sec 300` -> live 8080 run completed with truthful blocked evidence

Live 8080 evidence:

- `GET http://127.0.0.1:8080/v1/models` -> available, model `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`
- Project: `rv7-rubik-live`
- Workspace: `rv7-rubik-live`
- Pool ID: `pool_517501dbf0fe`
- Run ID: `atlas_run_0c39bcda53c5`
- Backend Run API executed and reached terminal status `failed`
- Final error: `patch_proposal_failed`
- Patch failure summary: `semantic_validation_failed:content_missing,satisfied_requirement_ids_missing,semantic_evidence_missing`
- Visual contract classification: `interactive_web_app_visual_v1`
- Artifact type: `interactive_web_app`
- Required signals: `page_loads`, `controls_exist`, `state_changes_on_interaction`
- Missing signals: `artifact_missing`
- `canvas_exists` was absent from required signals and absent from hard missing signals

Interpretation: RV7 did not pass because the live 8080 model failed to generate usable patch content for `index.html`; no artifact was written, so browser/runtime visual verification could not pass. The failure does not reproduce the old canvas over-requirement: the selected contract was non-canvas and `canvas_exists` was not a hard missing signal.

Runner behavior: unavailable model evidence is recorded as `blocked_live_llm_unavailable`, and reachable-model patch generation failure is recorded as `blocked_live_llm_patch_generation_failed`, not passed.

Safety invariants: UI/CLI authority was not expanded. The live flow used project creation, PlanPool creation, and backend Run API execution; it did not bypass Proposal, Safe Apply, Verification, or backend Run control. Browser smoke was recorded as skipped/static-only rather than passed.

Remaining gaps: RV8 final review and docs closeout.

Next package: RV8 — Final review and docs closeout

Blocker: live 8080 model produced no usable patch content for the Rubik HTML solver implementation.

Proof level: `live_8080_rubik_non_canvas_contract_blocked_patch_generation`

### RV8 — Final review and docs closeout (completed 2026-06-26)

Status: completed in this closeout PR

Changed files:

- `tools/run_atlas_restore_visual_recovery_eval.py`
- `tests/test_atlas_restore_visual_recovery_eval.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`
- `AGENTS.md`
- `Agent.md`
- `docs/AGENTS.md`

Validation:

- `python -m pytest -q tests\test_atlas_restore_visual_recovery_eval.py` -> 7 passed
- `python -m py_compile tools\run_atlas_restore_visual_recovery_eval.py tests\test_atlas_restore_visual_recovery_eval.py` -> passed
- `python tools\run_atlas_restore_visual_recovery_eval.py --final-review --input-json ca_data\atlas_restore_visual_recovery_eval\rv7_live_8080.json --output-json ca_data\atlas_restore_visual_recovery_eval\rv8_final_review.json --timeout-sec 120` -> passed

Final review evidence:

- Final review bundle includes focused tests, project isolation fixture result, localStorage scoped-key assertion, backend workspace isolation result, Rubik classification result, visual contract result, live 8080 result, and unavailable checks.
- 8080 advisory model: `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`
- Advisory verdict: `pass`
- Blocking issues: none
- Missing deterministic checks: none
- Contradictory evidence: none
- Notes confirm the RV7 live result is truthfully blocked by `blocked_live_llm_patch_generation_failed`, not passed, and that project scoping plus non-canvas visual-contract checks passed deterministically.

Closeout state: RV0-RV6 completed, RV7 truthfully blocked by live 8080 patch generation failure, and RV8 completed. The original cross-project restore leak is covered by client and backend scoped tests plus the E2E scenario. The Rubik HTML solver request selects a non-canvas interactive web app contract; `canvas_exists` is not required or hard-missing unless canvas is explicit.

Remaining gaps: none for RV0-RV8. Future work can improve weak-model patch generation quality for the Rubik implementation, but that is outside this restore/visual-contract recovery track because the blocked live run did not reproduce the canvas over-requirement.

Next package: none; RV0-RV8 is closed.

Blocker: none for closeout. RV7 remains truthfully blocked for live artifact generation because the local 8080 model produced no usable patch content.

Proof level: `rv0_rv8_closed_with_truthful_live_block`

## Required focused test matrix

Add/update as work lands:

### Follow-up: Runtime restore scope guard (completed 2026-06-27)

Status: completed in this working tree

Changed files:

- `app/api/atlas_pipeline.py`
- `web/js/atlas_pipeline_api.js`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_runtime_status_contract.py`
- `tests/test_atlas_runtime_status_panel_contract.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Behavior implemented: Atlas now records `workspace_id`, `runtime_scope_key`, and `runtime_scope` metadata on newly-created PlanPools and async plan-pool jobs. Project-scoped PlanPool JSON, markdown, job status, and runtime-status endpoints reject a stored pool/job before serializing renderable plan, failure, blocker, approval, or retry fields when the stored scope does not match the requested workspace. Legacy unscoped runtime state fails closed for concrete project workspaces.

Safe rejection payload: `runtime_restored=false`, `active_runtime=false`, `restored_state_rejected=true`, `restore_rejected_reason=project_scope_mismatch` or `missing_project_scope`, `requires_user_action=false`, `next_actions=["wait"]`. The UI passes `workspace_id` on pool/status reads and may show a bounded "restore ignored" notice without rendering foreign plan or approval/run controls.

Validation:

- `python -m pytest -q tests\test_atlas_runtime_status_contract.py` -> 10 passed
- `python -m pytest -q tests\test_atlas_runtime_status_panel_contract.py` -> 7 passed
- `python -m pytest -q tests\test_atlas_project_restore_isolation.py tests\test_atlas_project_restore_e2e_contract.py tests\test_atlas_continuation_workspace_isolation.py` -> 11 passed
- `python -m pytest -q tests\test_atlas_api_pipeline.py::test_get_plan_pool tests\test_atlas_api_pipeline.py::test_get_plan_pool_markdown tests\test_atlas_api_pipeline.py::test_pipeline_status_requires_pool_id_or_returns_422 tests\test_atlas_api_pipeline.py::test_pipeline_status_returns_saved_state tests\test_atlas_api_pipeline.py::test_pipeline_status_missing_state_returns_404` -> 5 passed
- `python -m py_compile app\api\atlas_pipeline.py tests\test_atlas_runtime_status_contract.py tests\test_atlas_runtime_status_panel_contract.py` -> passed
- `node --check web\js\atlas_claude_panel.js` -> passed
- `node --check web\js\atlas_pipeline_api.js` -> passed

Not counted as pass: `python -m pytest -q tests\test_atlas_plan_pool_project_binding.py tests\test_atlas_api_pipeline.py` and then `python -m pytest -q tests\test_atlas_plan_pool_project_binding.py` were stopped after hanging in the planning path with minimal output. The direct affected API read subset above passed.

Safety invariants: no runtime semantics, Proposal, Safe Apply, Verification, backend run order, Vue default/read-only status, `ui.html` default, execution capability, remote push, self-apply, raw source serving, or startup npm/Vite/Vue build behavior was changed.

### Follow-up: Server-authoritative execution progress indicators (completed 2026-06-27)

Status: completed in this working tree

Changed files:

- `app/api/atlas_runs.py`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_runtime_status_contract.py`
- `tests/test_atlas_runtime_status_panel_contract.py`
- `docs/atlas_project_restore_visual_recovery_plan.md`

Behavior implemented: `/api/atlas/runs/{run_id}/status` now returns read-only progress fields already owned by `AtlasRunState`: completed/failed/blocked/skipped item ids, per-status counts, `running_count`, and a backend-derived `item_progress` list synthesized from the saved PlanPool when available. The endpoint also returns tolerant `token_usage` metadata from latest run events, run metadata, or patch-generation lifecycle metadata, falling back to max-context-only data when token counts are unavailable.

UI behavior implemented: `watchBackendRun()` now renders backend `item_progress` through `renderPlanSteps()`, dispatches `atlas:llm-progress` from run status token data, and passes completed/failed/blocked/skipped counts plus current-item title into `renderRuntimeStatusPanel()`. The runtime panel no longer stays empty during a healthy running backend run; it shows compact progress, current item, token/context indicator when known, and live connection state.

Validation:

- `python -m pytest -q tests/test_atlas_runtime_status_contract.py` -> 17 passed
- `python -m pytest -q tests/test_atlas_runtime_status_panel_contract.py` -> 9 passed
- `python -m pytest -q tests/test_atlas_run_api.py tests/test_atlas_run_orchestrator.py tests/test_atlas_run_item_selection.py tests/test_atlas_run_retry_revise.py tests/test_atlas_run_lease_recovery.py` -> 29 passed
- `python -m pytest -q tests/test_atlas_run_control_hardening_eval.py tests/test_atlas_run_cli.py tests/test_atlas_run_api.py tests/test_atlas_run_schema.py tests/test_atlas_run_retry_revise.py tests/test_atlas_run_item_selection.py tests/test_atlas_run_lease_recovery.py tests/test_atlas_run_orchestrator.py` -> 46 passed
- `python -m py_compile app/api/atlas_runs.py tests/test_atlas_runtime_status_contract.py tests/test_atlas_runtime_status_panel_contract.py` -> passed
- `node --check web/js/atlas_claude_panel.js` -> passed
- `node --check web/js/atlas_pipeline_api.js` -> passed

Safety invariants: this follow-up restores display of server-owned state only. It does not change runtime semantics, approval conditions, clarification blockers, autonomous preflight, backend item order, Proposal, Safe Apply, Verification, retry policy, execution capability, Vue authority/defaults, direct client-side execution authority, remote push, self-apply, raw source serving, fallback redirects, or startup npm/Vite build behavior.

```text
python -m pytest -q tests/test_atlas_project_restore_isolation.py
python -m pytest -q tests/test_atlas_project_picker_bootstrap_contract.py
python -m pytest -q tests/test_atlas_continuation_workspace_isolation.py
python -m pytest -q tests/test_atlas_visual_rubik_contract.py
python -m pytest -q tests/test_atlas_visual_failure_diagnostics.py
python -m pytest -q tests/test_atlas_project_restore_e2e_contract.py
python -m pytest -q tests/test_atlas_restore_visual_recovery_eval.py
```

Affected existing tests:

```text
python -m pytest -q tests/test_atlas_inflight_resume_recovery_contract.py
python -m pytest -q tests/test_atlas_runtime_status_panel_contract.py
python -m pytest -q tests/test_atlas_api_pipeline.py
python -m pytest -q tests/test_atlas_auto_verification_service.py
python -m pytest -q tests/test_atlas_visual_contract_registry.py
python -m pytest -q tests/test_visual_contract_matrix.py
python -m pytest -q tests/test_atlas_run_api.py
python -m pytest -q tests/test_atlas_run_orchestrator.py
```

Syntax checks:

```text
node --check web/js/atlas_claude_panel.js
node --check web/js/app.js
node --check web/js/atlas_pipeline_api.js
python -m py_compile agent/atlas_auto_verification_service.py agent/atlas_visual_requirement_normalizer.py agent/atlas_visual_task_classifier.py agent/atlas_visual_contract_registry.py agent/atlas_visual_artifact_verifier.py agent/atlas_playwright_smoke_verifier.py app/api/atlas_pipeline.py
```

## Completion definition

This recovery is complete only when:

- new project creation cannot display another project's PlanPool;
- localStorage plan/run/event hints are project-scoped or ignored when active project exists;
- project picker bootstrap loads the selected project into Atlas panel;
- backend continuation latest is verified workspace-scoped;
- Rubik HTML solver does not require canvas by default;
- explicit canvas requests still verify canvas correctly;
- visual failure cards show the selected contract and classification context;
- the exact mobile-observed scenario is covered by deterministic tests;
- 8080 live validation passes or truthfully blocks;
- final evidence review is written.
