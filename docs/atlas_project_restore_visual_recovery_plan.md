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
| RV2 | Bootstrap order and selected-project load | pending | |
| RV3 | Backend continuation/recovery workspace isolation audit | pending | |
| RV4 | Rubik / cube visual classification fix | pending | |
| RV5 | Visual verifier contract evidence and UI diagnostics | pending | |
| RV6 | End-to-end project isolation scenario | pending | |
| RV7 | Live 8080 Rubik validation | pending | |
| RV8 | Final review and docs closeout | pending | |

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

Status: completed locally; PR pending

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

## Required focused test matrix

Add/update as work lands:

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
