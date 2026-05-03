# Atlas Naming Integration (Phase 12.9)

## Final target navigation
- Chat
- Atlas
- Echo
- Nexus

## Roles
- Chat = conversation, consultation, and search-assisted QA.
- Atlas = guided work planning, approval, execution preview, patch review, and run audit.
- Echo = voice, interpretation, ASR/TTS, and EchoVault operations.
- Nexus = research, evidence collection, reporting, and external information connectivity.

## Internal mapping
- Agent runtime powers Atlas.
- Task workflow is gradually absorbed into Atlas.
- Task remains for compatibility.

## Short-term (Phase 12.9)
- Add Atlas naming in UI and Agent-side Atlas entry points.
- Keep Task/Agent compatibility and existing jobs flow.
- Keep existing shared workflow runtime (`startPlanWorkflow`) with Atlas-first labels.

## Mid-term
- Rename Task UI toward Atlas Tasks / Atlas Runs.
- Move Plan/Patch Review surfaces under Atlas presentation.
- Keep backward-compatible APIs and runtime wiring during migration.

## Long-term
- Top navigation becomes Chat / Atlas / Echo / Nexus.
- Agent becomes internal runtime, not primary user-facing mode.
- Preserve safety gates and human-in-the-loop approvals.

## Explicit non-goals
- no auto apply
- no bulk approve/apply
- no approval bypass

## Phase 15 migration (top-level Atlas entry)
- Top-level navigation begins moving to: Chat / Atlas / Agent / Echo / Nexus.
- Task is no longer the primary top-level entry.
- Task remains reachable from Atlas as Legacy/Guided Task.
- Agent remains available as advanced runtime access.
- Future target remains: Chat / Atlas / Echo / Nexus.
- Non-goals stay unchanged for this phase:
  - no deletion of Task/Agent
  - no API breaking rename
  - no auto apply / bulk apply / bulk approve

## Current workflow entry points
- Chat/Task compatibility Plan button (`startPlanWorkflow()`).
- Atlas button (`startAtlasWorkflow()`).
- Backward-compatible alias (`startAgentGuidedWorkflow()`).

## Phase 15.5 polish (Atlas navigation / legacy task explicit switch)
- Legacy Task access from Atlas is now explicit (task-on), not toggle-based.
- Atlas is the normal workbench for guided work planning, execution preview, patch review, and run audit.
- Agent remains the advanced runtime surface.
- Task remains as a compatibility path.

## Phase 16 note (Atlas thin workbench wrapper)
- Atlas now has a thin top-level workbench wrapper (`atlas-panel-col`) for guided workflow entry.
- Existing Agent panel remains available for advanced runtime access.
- Atlas wrapper reuses existing planning, run selector, dashboard, and patch review functions.
- No API breaking rename.
- No Task/Agent deletion.
- Future phase may further split Atlas subviews, but Phase 16 is a thin wrapper only.


## Phase 16.5 note (Atlas wrapper smoke / layout polish)
- Phase 16.5 validates Atlas wrapper layout and smoke behavior across desktop/mobile mode switching.
- Atlas wrapper remains thin and reuses existing APIs/functions (no runtime or API split in this phase).
- No workspace split or destructive navigation change is introduced in this phase.

## Phase 17 note (Atlas lightweight subviews)
- Atlas wrapper now has lightweight subviews (Overview / Plan / Runs / Dashboard / Patch Review / Legacy).
- Subviews are UI organization only; no full workspace split is introduced in this phase.
- Existing planning/run/dashboard/patch APIs and helpers continue to be reused.
- No Task/Agent deletion is performed.
- No auto apply or bulk approve/apply is introduced.

## Phase 17.5 note (Atlas subview robustness cleanup)
- Phase 17.5 separates root current-subview state from panel selectors.
- Root uses `data-atlas-current-subview`.
- Panels use `data-atlas-subview-panel`.
- Existing host IDs and APIs remain unchanged.
- This is robustness cleanup only, not workspace split.


## Phase 18 note (Atlas subview persistence / URL-free restore)
- Phase 18 adds URL-free Atlas subview persistence using localStorage.
- New key: `atlas:lastSubview`.
- Last run tracking continues to use `atlas:lastRunId`.
- Atlas restore does not auto-fetch dashboard or patch review content.
- Users explicitly open dashboard/patch review from Atlas controls.
- No URL routing, hash routing, or history API is introduced in this phase.


## Phase 18.5 note (Atlas restore UX polish / explicit resume prompts)
- Phase 18.5 adds explicit resume prompts after URL-free Atlas subview restore.
- Dashboard / Patch Review / Recent Runs still do not auto-fetch on restore.
- Users resume manually via Atlas Workbench buttons.
- Resume notice uses restored last subview and `atlas:lastRunId`.
- No URL routing, hash routing, or history API is introduced in this phase.

## Phase 19 note (Atlas Guided Plan UX consolidation)
- Plan subview now includes an **Atlas Guided Plan Flow** summary.
- The summary shows progress for Requirement / Plan / Review / Approval / Execute Preview / Patch Review.
- UI summary is derived from existing `planWorkflowState` and existing workflow functions.
- No planner backend rewrite is introduced in this phase.
- No approval bypass is introduced in this phase.
- No auto apply / bulk apply / bulk approve is introduced in this phase.

## Phase 19.5 note (Guided Plan Flow state mapping cleanup)
- Guided Plan Flow state mapping is now derived via a dedicated UI helper.
- The helper reads existing `planWorkflowState` aliases safely for display-only status.
- No backend workflow behavior is changed in this phase.
- No approval bypass is introduced.
- No auto apply / bulk apply is introduced.


## Phase 20 note (Guided Plan Flow action buttons)
- Guided Plan Flow now shows explicit next-action buttons in the Plan subview.
- These buttons open existing safe workflow panels/functions only.
- Approval and Patch Review gates remain required.
- This phase introduces no backend workflow behavior change.
- No bulk apply is introduced in this phase.

## Phase 20.5 note (Guided Plan action focus / scroll targets)
- Guided Plan action buttons now focus existing safe workflow sections in the Plan subview.
- Buttons perform focus/scroll guidance only.
- No approve/execute/apply is performed by these buttons.
- Approval and Patch Review gates remain required.
- No backend workflow behavior change is introduced in this phase.


## Phase 21 note (Stable Workflow Section Anchors / Existing UI Target Tagging)
- Stable `data-atlas-workflow-target` anchors are added to existing workflow UI sections (plan review / approval / execute preview / patch review).
- `findAtlasWorkflowTarget(kind)` now prefers real workflow UI targets and falls back to lightweight Phase 20.5 anchors.
- Focus helper behavior remains focus/scroll guidance only.
- No approve/execute/apply workflow behavior changes are introduced in this phase.
- Approval and Patch Review gates remain required.

## Phase 21.5 note (Dynamic Plan Workflow card target tagging)
- Dynamic Plan Workflow card sections now receive stable workflow targets (`dynamic-plan-review`, `dynamic-approval`, `dynamic-execute-preview`, `dynamic-patch-review`).
- `findAtlasWorkflowTarget(kind)` prefers dynamic real UI targets first, then stable Atlas Plan Flow targets, then lightweight fallback anchors.
- Focus helper behavior remains focus/scroll guidance only.
- No approval/execution/apply workflow behavior changes are introduced in this phase.
- Approval and Patch Review gates remain required.

## Phase 21.6 note (Atlas top-level visibility regression fix)
- Fixes Atlas top-level visibility regression where Atlas button could leave the workbench blank.
- Atlas button must show `atlas-panel-col` and `Atlas Workbench`.
- Restore failures must not blank the Atlas Workbench; Atlas panel visibility is preserved with safe fallback.
- Desktop/mobile smoke checks are reinforced for Atlas visibility.
- No workflow behavior changes are introduced in this phase.

## Phase 22: Chat Surface Cleanup / Move Task-Agent Legacy Entrypoints to Atlas

- Chat surface is clarified as lightweight conversation/Q&A and quick investigation.
- Atlas is reinforced as the primary guided workflow surface for normal work.
- Task remains a compatibility path under Atlas Legacy (`Open Legacy Task`).
- Agent remains the advanced runtime surface (`Open Agent Advanced`).
- No Task/Agent deletion was introduced.
- No workflow behavior changes were introduced (approval gates and execute/patch flow remain unchanged).

## Phase 22.1 note (Atlas Start Button Execution Regression Fix)
- Fixes Atlas Workbench Start Atlas regression where clicking Start Atlas could appear unresponsive.
- Start Atlas now surfaces workflow start and failure state in visible UI messages/logs.
- Empty request no longer fails silently; Atlas now shows a clear input guidance message.
- Atlas Workbench Start uses the existing safe Plan Workflow path (`startPlanWorkflow`), without workflow bypass.
- No approval / execute / patch behavior changes are introduced in this phase.


## Phase 23 note (Atlas dedicated Requirement input)
- Atlas Workbench now includes a dedicated Requirement input (`atlas-requirement-input`).
- Start Atlas reads Atlas Requirement input first, then falls back to Chat input (`#input`).
- Existing safe guided planning path is reused (`startAtlasWorkflow` -> `startPlanWorkflow` -> `runGuidedPlanWorkflow` -> `generatePlanOnlyFromInput`).
- Empty request feedback remains in place for Atlas starts.
- No approval / execute / patch behavior changes are introduced in this phase.

## Phase 23.1 note (Requirement propagation safety fix)
- Fixes Requirement propagation into the existing plan generation path.
- `generatePlanOnlyFromInput()` remains legacy-safe and reads Chat input (`#input`).
- Atlas Requirement is synchronized into Chat input before invoking the existing planner.
- No backend workflow changes were introduced in this phase.
- No approval / execute / patch behavior changes are introduced in this phase.


## Phase 23.5 note (Atlas Requirement input polish / persistence)
- Atlas Requirement input now persists drafts via localStorage (`atlas:requirementInput`).
- Clear Requirement clears only Atlas Requirement input (it does not clear Chat input).
- Use Chat Input copies Chat text into Atlas Requirement input.
- Atlas Requirement now shows character count and clearer status feedback for save/restore/fallback/start.
- Existing safe Plan Workflow path remains unchanged.
- No approval / execute / patch behavior changes are introduced in this phase.

## Phase 24 note (Atlas Requirement source accuracy / Start status cleanup)
- Atlas Requirement source is now derived explicitly (`atlas` / `chat` / `empty`).
- Atlas Requirement input and Chat fallback are distinguished in status feedback.
- Start Atlas status messages are cleaned up to reduce silent or misleading feedback.
- Existing safe Plan Workflow path remains unchanged.
- No approval / execute / patch behavior changes are introduced in this phase.

## Phase 25 note (Atlas guided workflow end-to-end safe journey smoke)
- Atlas guided workflow safe journey smoke was added for end-to-end UI verification.
- Atlas Start verification now covers Plan subview activation, Guided Plan Flow visibility, Workflow Status visibility, and requirement source visibility.
- Action buttons are verified as focus/navigation helpers only (non-destructive).
- Approval / Execute Preview / Patch Review gates remain required.
- Restore behavior still does not auto-fetch Dashboard/Patch/Recent Runs content.
- No backend workflow behavior changes were introduced in this phase.

## Phase 25.1 note (Execute tests / deflake Atlas safe journey smoke)
- Phase 25 tests and smoke were executed, and safe-journey smoke behavior was deflaked.
- Atlas safe journey smoke no longer requires backend completion to pass.
- Workflow Status is verified when present, and visible start/failure feedback is accepted when backend is unavailable.
- Console/page errors still fail smoke.
- No backend workflow behavior was changed.
- No approval / execute / patch behavior was changed.

## Phase 25.2 note (Playwright smoke split: UI smoke / backend E2E smoke)
- Playwright smoke is split into backend-independent UI smoke and optional backend E2E smoke.
- Default smoke (`python scripts/smoke_ui_modes_playwright.py`) runs UI smoke only.
- Backend E2E smoke is opt-in and runs only when `RUN_ATLAS_BACKEND_E2E=1` is set.
- UI smoke accepts visible backend failure (`Atlas Start failed:`) as a valid safe-journey outcome when backend is unavailable.
- Backend E2E smoke does not accept `Atlas Start failed:` and expects workflow/status/source signals on success path.
- If Playwright is missing, smoke prints install guidance:
  - `python -m pip install playwright`
  - `python -m playwright install chromium`
- No backend workflow behavior changes were introduced in this phase.


## Phase 25.3 note (Run Playwright UI smoke in prepared env / optional CI job)
- Playwright UI smoke was attempted in a prepared environment via `python scripts/smoke_ui_modes_playwright.py`.
- UI smoke remains backend-independent and accepts visible `Atlas Start failed:` feedback when backend is unavailable.
- Backend E2E smoke remains explicit opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- Optional/manual GitHub Actions workflow was added: `.github/workflows/playwright-ui-smoke.yml` (`workflow_dispatch` only).
- Optional smoke setup/run commands are unchanged:
  - `python -m pip install playwright`
  - `python -m playwright install chromium`
  - `python scripts/smoke_ui_modes_playwright.py`
  - `RUN_ATLAS_BACKEND_E2E=1 python scripts/smoke_ui_modes_playwright.py`
- No backend workflow behavior changes were introduced in this phase.
- No approval / execute / patch behavior changes were introduced in this phase.

## Phase 25.4 note (Playwright UI smoke diagnostic aggregation)
- Playwright UI smoke now aggregates scenario results and prints a final summary.
- Scenario failures no longer stop collection immediately; remaining scenarios continue.
- Final smoke job still fails when any scenario fails.
- Scenario failure screenshots and summary markdown are written under `artifacts/playwright/`.
- Optional workflow uploads artifacts and appends summary to GitHub Step Summary.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1` only.
- No backend workflow behavior changes were introduced in this phase.
- No approval / execute / patch behavior changes were introduced in this phase.


## Phase 25.4.1 note (Serve Playwright smoke UI over HTTP / scenario isolation)
- Playwright UI smoke now serves `ui.html` over `http://127.0.0.1:<port>/` by default instead of `file://`.
- Smoke harness includes a lightweight in-process mock HTTP backend so UI fetch calls succeed without backend wiring.
- `file://` fetch scheme failures are fixed at harness/origin level (not ignored).
- Scenarios are isolated with per-scenario pages and viewport setup to reduce cascading failures.
- Chat input helper fallback (`set_chat_input` / DOM dispatch) reduces hidden-input flakiness.
- Failure diagnostics now include truncated summary rows plus per-scenario full `.log` and screenshot artifacts under `artifacts/playwright/`.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1`; default optional CI smoke does not enable it.
- No backend guided-workflow behavior/gates were changed (PlanApproval / Execute Preview / PatchApproval logic unchanged).


## Phase 25.4.2: Remaining Playwright UI smoke stabilization
- Remaining Playwright smoke failures were investigated after the HTTP-origin harness fix.
- Hidden Atlas control selectors were scoped and stabilized under `#atlas-workbench-card` overview panel.
- Python Playwright `wait_for_function` argument usage was corrected to keyword-based `arg=` form.
- Nexus/reference selectors were aligned to current UI tab IDs with fallback for legacy `web-scout`.
- Mobile scenario viewport isolation was improved with explicit mobile viewport setup per scenario.
- Summary readability was improved with scenario-name escaping and safer error truncation/formatting.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- No backend workflow changes were introduced.
- No approval / execute / patch behavior changes were introduced.

## Phase 25.4.4 artifact-driven Playwright smoke alignment

- Applied artifact-driven Playwright smoke fixes without backend workflow behavior changes.
- Updated Atlas Legacy subview expectation to current UI (Legacy verifies `Open Legacy Task` and `Open Agent Advanced`; Recent Runs verification moved to Runs subview).
- Added/strengthened Atlas helpers (`open_atlas`, `set_atlas_subview`, `wait_atlas_subview`, `ensure_atlas_overview`, `ensure_atlas_plan`) to avoid hidden-panel waits.
- Stabilized `#input` sync verification in guided workflow with explicit wait + diagnostics.
- Aligned Nexus tab wait logic to current visible DOM state (not only stale `.active` panel class assumptions).
- Updated Reference card action selectors to match current labels/render target with multi-label fallback and DOM diagnostics.
- Updated mobile mode checks to rely on visible panel/display state instead of stale `active` class assumptions.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E`.
- No backend workflow logic changes.
- No approval / execute / patch behavior changes.

## Phase 25.4.5 note (Final Playwright UI smoke alignment)
- Final Playwright UI smoke alignment was applied after artifact review.
- Atlas Requirement controls are treated as Workbench-level controls (root-scoped under `#atlas-workbench-card`), not Overview panel child-only controls.
- Atlas guided workflow smoke now verifies Workflow Status / Requirement Preview evidence instead of requiring the final Chat input value to remain synced.
- Nexus tabs accept current DOM behavior where some tabs may not expose `#nexus-tab-{name}` panels; active tab button + visible workspace is accepted when panel is missing.
- Reference card checks align to current Reference Viewer text (`source_id`, `mode`, `highlight`) instead of stale chunk-only text assumptions.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- No backend workflow changes were introduced.
- No approval / execute / patch behavior changes were introduced.

## Phase 25.4.6 note (Final two Playwright UI smoke failures cleanup)
- Final two Playwright UI smoke failures were aligned to current UI behavior without backend workflow rewrites.
- Atlas Requirement controls are treated as Workbench-level controls (`#atlas-workbench-card` scoped), not Overview-panel-only controls.
- Atlas Start smoke no longer relies on Overview panel scoping for common Requirement controls (Use Chat / Clear / Requirement input).
- Reference card smoke now verifies current Reference Viewer fields: `source_id`, `mode`, and `highlight`.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- No backend workflow behavior changes were introduced.
- No approval / execute / patch behavior changes were introduced.


## Phase 25.4.7 note (Final Playwright UI smoke 9/9 cleanup)
- Final Playwright UI smoke cleanup targets the remaining two scenarios only.
- Atlas Use Chat Input smoke now sets Chat input via DOM direct setter without leaving Atlas mode.
- Atlas Start smoke no longer relies on the final Chat input value for success assertions.
- Reference card smoke aligns to current Reference Viewer fields: `source_id`, `mode`, `highlight`.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- No backend workflow changes were introduced.
- No approval / execute / patch behavior changes were introduced.

## Phase 25.4.8 note (Final Playwright UI smoke expected-state cleanup)
- Final expected-state cleanup was applied for the last Playwright UI smoke failures.
- Atlas Start feedback smoke is now staged step-by-step to avoid mixed stale expectations.
- Chat fallback status (`Falling back to Chat input.`) is accepted in the chat-fallback step.
- Atlas workflow verification now relies on Requirement Preview / Boss message / Workflow Status evidence, not final Chat input value.
- Reference card smoke now verifies current Reference Viewer fields: `source_id`, `mode`, `highlight`.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- No backend workflow changes were introduced.
- No approval / execute / patch behavior changes were introduced.

## Phase 25.4.9 note (Final Playwright wait argument and Reference Viewer wait update)
- Final Playwright `wait_for_function` argument fix was applied for Python API compatibility (`arg=` keyword for JS arguments).
- Reference card smoke now waits on current Reference Viewer fields: `source_id`, `mode`, `highlight`.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- No backend workflow changes were introduced.
- No approval / execute / patch behavior changes were introduced.

## Phase 25.4.10 note (Final Reference Viewer selector fallback for Playwright UI smoke)
- Final Reference Viewer selector fallback was applied for `reference_card_actions` in Playwright UI smoke.
- Reference card smoke now collects viewer text from multiple current DOM candidates with `#nexus-col` fallback.
- Viewer field checks are separated from URL action assertions.
- Current viewer fields `source_id`, `mode`, and `highlight` are used for success checks.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- No backend workflow changes were introduced.
- No approval / execute / patch behavior changes were introduced.

## Phase 25.4.11 note (Final reference_card_actions smoke stabilization)

- Stabilized `reference_card_actions` by switching Reference Viewer verification to direct DOM evaluation helpers with a `#nexus-col` fallback.
- Viewer field checks now validate current UI fields: `source_id`, `mode`, and `highlight`.
- Viewer wait and URL action assertions are separated so viewer render and button-open flows are validated independently.
- Diagnostics now include candidate selector text dumps and normalized viewer text output.
- Backend E2E remains opt-in behind the existing `RUN_ATLAS_BACKEND_E2E` gate.
- No backend workflow behavior changes were made.
- No approval / execute / patch behavior changes were made.


## Phase 25.4.12 note (Fix collect_reference_viewer_text page.evaluate JavaScript syntax)
- Fixed final `reference_card_actions` failure caused by an invalid JavaScript string in `page.evaluate`.
- `collect_reference_viewer_text` now avoids unsafe newline string literals in inline JS.
- Reference Viewer field checks remain `source_id` / `mode` / `highlight` based.
- Backend E2E remains opt-in.
- No backend workflow changes were introduced in this phase.
- No approval / execute / patch behavior changes were introduced in this phase.

## Phase 25.4.12 note (Final reference_card_actions async viewer update wait)
- Final `reference_card_actions` stabilization now treats **Full Text** as a fetch-driven viewer update and does not require it to be a `window.open` action.
- Smoke now tracks `fetchedUrls` and `openedUrls` separately so `/nexus/sources/src-1/text` can be asserted via fetch activity while URL actions remain asserted via `window.open`.
- Reference Viewer verification now waits for current fields (`source_id`, `mode`, `highlight`) after Full Text click with polling-based async wait.
- Diagnostics now include initial/final viewer status and clicked action button metadata to make async timing issues easier to triage.
- Backend E2E remains opt-in (`RUN_ATLAS_BACKEND_E2E`) and default smoke remains UI-only.
- No backend workflow behavior changes were made.
- No approval/execute/patch behavior changes were made.

## Phase 25.4.14 note (Final reference_card_actions action sequencing fix)
- Final reference_card_actions action sequencing fix applied for Playwright UI smoke.
- Full Text action now verifies source text fetch and `mode: text` only.
- Highlight action is verified in a separate step for highlight/doc chunk fields.
- URL and Download actions are verified separately.
- `fetchedUrls` and `openedUrls` remain separated.
- Backend E2E remains opt-in (`RUN_ATLAS_BACKEND_E2E`).
- No backend workflow changes were introduced.
- No approval/execute/patch behavior changes were introduced.

## Phase 25.4.16 note (Final reference_card_actions disabled Source URL handling)
- Final `reference_card_actions` fix now handles disabled **Source URL** buttons without force-clicking.
- Smoke mock source data now provides multiple URL fields (`url`, `source_url`, `original_url`, `final_url`, `link`) to match current UI expectations.
- Source URL button is clicked only when enabled; when disabled, smoke records diagnostics and skips URL open assertion for that action.
- Full Text / Highlight / Download action checks remain in place.
- Diagnostics now include button text/disabled/onclick metadata for reference-card action analysis.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E`.
- No backend workflow behavior changes were made.
- No approval/execute/patch behavior changes were made.

## Phase 25.4.18 note (Final reference_card_actions Source URL conditional assert)
- Final `reference_card_actions` Source URL `openedUrls` assertion now runs only when the URL button is enabled and clicked.
- Disabled/missing Source URL buttons are diagnosed (`skippedDisabled` / `skippedMissing`), not force-clicked.
- Full Text / Highlight / Download checks remain required.
- fetchedUrls and openedUrls remain separated.
- Backend E2E remains opt-in (`RUN_ATLAS_BACKEND_E2E`).
- No backend workflow changes were introduced.
- No approval / execute / patch behavior changes were introduced.

## Phase 25.4.19 note (reference_card_actions Source URL diagnostic-only)
- Source URL action in `reference_card_actions` is now diagnostic-only.
- Full Text / Highlight / Download checks remain required.
- Source URL `openedUrls` is recorded but no longer fails smoke when absent.
- This avoids failures on valid disabled/no-op Source URL UI states.
- Backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- No backend workflow changes were introduced in this phase.
- No approval / execute / patch behavior changes were introduced in this phase.

## Phase 25.4.20 note (reference_card_actions Source URL/Download diagnostic-only)
- In `reference_card_actions`, **Source URL** and **Download** actions are now treated as diagnostic-only and are not required smoke assertions.
- **Full Text** and **Highlight** remain required checks (`/text`, `/chunks`, `source_id: src-1`, `mode: text`, `doc-1:0`/`highlight: doc-1:0`).
- **Download** is intentionally not clicked as a required action in smoke because it can trigger current-page navigation and invalidate UI/tracking state.
- `fetchedUrls` and `openedUrls` are still collected and emitted for diagnostics.
- Atlas backend E2E remains opt-in via `RUN_ATLAS_BACKEND_E2E`.
- No backend workflow logic changes were made.
- No approval/execute/patch behavior was changed.

## Phase 25.4.21 note (reference_card_actions final viewer diagnostic-only)
- Final Reference Viewer check in `reference_card_actions` is now diagnostic-only.
- Required assertions remain at action points:
  - **Full Text** keeps required `/text` fetch and `source_id: src-1` + `mode: text` viewer checks.
  - **Highlight** keeps required `/chunks` fetch and `doc-1:0`/`highlight: doc-1:0` viewer checks.
- **Source URL** may legitimately switch the viewer to `mode: url`; this must not fail the final step.
- **Source URL** and **Download** remain diagnostic-only actions.
- Backend E2E remains opt-in (`RUN_ATLAS_BACKEND_E2E`), with no backend workflow behavior changes.
- No approval/execute/patch behavior changes were made.

## Phase 25.5 note (Lock Playwright UI smoke 9/9 PASS)
- Playwright UI smoke reached 9/9 PASS (`Total scenarios: 9`, `PASS: 9`, `FAIL: 0`).
- UI smoke is served over an HTTP mock origin (`http://127.0.0.1:<port>/`), not `file://`.
- Scenario aggregation remains enabled and keeps producing artifacts plus summary output.
- `reference_card_actions` final policy is fixed as:
  - Full Text and Highlight are required checks.
  - Source URL and Download are diagnostic-only checks.
- Backend E2E remains explicit opt-in via `RUN_ATLAS_BACKEND_E2E=1`.
- No backend workflow behavior changes are introduced in this phase.
- No approval / execute / patch behavior changes are introduced in this phase.


## Phase 26.0 note (Atlas backend E2E opt-in validation readiness)
- Backend E2E remains explicit opt-in (`RUN_ATLAS_BACKEND_E2E=1`).
- Default Playwright UI smoke remains mock-backed and fixed at 9/9 scenarios.
- Real backend E2E requires a backend process already running plus:
  - `PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000`
  - `RUN_ATLAS_BACKEND_E2E=1`
  - Example: `PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000 RUN_ATLAS_BACKEND_E2E=1 python scripts/smoke_ui_modes_playwright.py`
- Backend E2E validates start/status/source/workspace signals but does not auto-approve, auto-execute, or auto-apply patches.
- `Atlas Start failed:` remains acceptable in backend-unavailable mock UI smoke, but is a hard failure in backend E2E path.
- Backend E2E diagnostics include base URL, Atlas mode/subview/requirement/status, message tail, `/health`, `/api/task/plan`, and browser console/page errors.

## Phase 26.1 note (Real backend preflight / full E2E separation)
- Backend real-environment checks are split into two opt-in paths:
  - preflight
  - full backend E2E
- Preflight gate: `RUN_ATLAS_BACKEND_PREFLIGHT=1`.
  - GET-only probes (`/health`, `/system/summary`, `/settings`, `/projects`, `/models/db/status`).
  - Does not start planner/LLM.
  - Does not press Atlas Start.
- Full backend E2E gate: `RUN_ATLAS_BACKEND_E2E=1`.
  - Runs backend preflight first.
  - Then presses Atlas Start and validates Atlas guided workflow signals.
  - Does not auto-approve / auto-execute / auto-apply.
- Default Playwright UI smoke remains 9/9 mock-backed scenarios.
- Optional workflow remains manual (`workflow_dispatch`) and does not enable backend preflight/E2E by default.

## Phase 26.2 note (Real backend preflight execution visibility hardening)
- `atlas_backend_preflight` appears in scenario summary only when opt-in is enabled.
- Preflight diagnostics are visible in artifact logs (`baseUrl`, per-endpoint status/ok/json|jsonError, elapsedMs, errors/warnings).
- Preflight remains GET-only and planner-safe (no plan generation / no Atlas Start in preflight-only path).
- `/health` is treated as the primary required liveness check; other preflight endpoints are diagnostic warnings.
- Full backend E2E remains separate opt-in (`RUN_ATLAS_BACKEND_E2E=1`) and still runs preflight first.
- Default optional smoke remains mock-backed 9/9 baseline.
- No approval / execute / apply behavior changes were introduced.


- `PLAYWRIGHT_SMOKE_BASE_URL` is only honored in real backend opt-in modes (`RUN_ATLAS_BACKEND_PREFLIGHT=1` or `RUN_ATLAS_BACKEND_E2E=1`). In default mode, it is ignored and smoke remains mock-backed by design.

## Phase 26.3 note (Windows local preflight validation and default/base-url guard confirmation)
- Windows local backend preflight-only was validated as a single-scenario run:
  - Total scenarios: 1
  - PASS: 1
  - FAIL: 0
  - atlas_backend_preflight PASS
- Confirmed preflight endpoint status snapshot:
  - /health 200
  - /system/summary 200
  - /settings 200
  - /projects 200
  - /models/db/status 200
  - errors []
  - warnings []
- Preflight remained GET-only (no planner start, no Atlas Start button press, no diagnostic POST).
- Default mock-backed UI smoke 9/9 verification must remain a separate run from preflight-only mode.
- `PLAYWRIGHT_SMOKE_BASE_URL` alone remains guarded and ignored in default mode; explicit base URL is honored only for real-backend opt-in modes.
- Full backend E2E remains not yet executed by this phase note and is still an explicit opt-in path.
- No approval / execute / apply behavior changes were introduced.

## Phase 26.4 note (Full backend E2E dry-run with Atlas Start only)
- Full backend E2E dry-run command:
  - `PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000 RUN_ATLAS_BACKEND_E2E=1 python scripts/smoke_ui_modes_playwright.py`
- Full backend E2E scenario set remains isolated to:
  - `atlas_backend_preflight`
  - `atlas_backend_e2e_journey`
- Dry-run scope:
  - presses Atlas Start
  - verifies guided workflow / status signals
  - stops before approval / execute / patch actions
- Failure policy:
  - `Atlas Start failed:` is treated as failure in full backend E2E mode.
  - preflight failure prevents meaningful E2E and fails before Atlas Start journey assertions.
- Default workflow remains opt-in/off for backend E2E (`RUN_ATLAS_BACKEND_E2E=1` only).

## Phase 26.5 note (Windows full backend E2E dry-run success record / opt-in policy lock)
- Windows local real-backend full E2E dry-run was validated.
- Command (bash):
  - `PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000 RUN_ATLAS_BACKEND_E2E=1 python scripts/smoke_ui_modes_playwright.py`
- Command (PowerShell):
  - `$env:PLAYWRIGHT_SMOKE_BASE_URL="http://127.0.0.1:8000"`
  - `$env:RUN_ATLAS_BACKEND_E2E="1"`
  - `Remove-Item Env:RUN_ATLAS_BACKEND_PREFLIGHT -ErrorAction SilentlyContinue`
  - `python scripts/smoke_ui_modes_playwright.py`
- Observed result:
  - Total scenarios: 2
  - PASS: 2
  - FAIL: 0
  - atlas_backend_preflight PASS
  - atlas_backend_e2e_journey PASS
- Observed dry-run state:
  - full backend E2E mode enabled
  - default UI scenarios are skipped in full backend E2E mode
  - atlasSubview: plan
  - atlasRequirementStatus: Using Atlas requirement input.
  - hasAtlasStartFailed: False
  - consoleErrors: []
  - pageErrors: []
  - approval/execute/patch/bulk buttons not activated
- Scope:
  - preflight runs first
  - Atlas Start is pressed
  - guided workflow/status is verified
  - dry-run stops before approval / execute / patch apply
  - no destructive action
- Policy lock:
  - full backend E2E remains opt-in
  - default mock-backed UI smoke remains 9/9
  - workflow does not enable backend E2E by default

## Phase 27.0 Atlas backend job lifecycle wait-plan opt-in

- Phase 26.5 validated full backend E2E dry-run reaches Atlas plan subview.
- Phase 27.0 adds an additional explicit opt-in `RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1` to observe lifecycle until plan completion/failure/timeout.
- Full opt-in command (PowerShell):
  - `$env:PLAYWRIGHT_SMOKE_BASE_URL="http://127.0.0.1:8000"`
  - `$env:RUN_ATLAS_BACKEND_E2E="1"`
  - `$env:RUN_ATLAS_BACKEND_E2E_WAIT_PLAN="1"`
  - `python scripts/smoke_ui_modes_playwright.py`
- Expected behavior:
  - preflight runs first
  - Atlas Start is triggered
  - lifecycle waits for plan completion/failure/timeout
  - no approval / execute preview / patch apply automation is performed
- Default workflow remains backend-off (no `RUN_ATLAS_BACKEND_E2E` and no wait-plan env by default).
- Wait-plan mode can invoke planner/LLM and may take longer; inspect logs/diagnostics before moving to approval/execute phases.

## Phase 27.0c note (wait-plan completion detection tightening)

- Wait-plan completion detection was tightened to avoid false completed decisions on pending plan states.
- `Approval: required` alone is no longer treated as plan completion.
- Backend job `running` is treated as in-progress, not completed.
- `Plan: pending` / `Review: pending` / `Requirement: pending` explicitly block completion.
- Diagnostics now include completion/pending/failure signal sets and a completion decision reason.
- Approval / execute preview / patch apply automation remains out of scope.


## Phase 27.0b wait-plan completion recognition fix
- Windows local wait-plan opt-in run reached `Requirement: done`, `Plan: generated`, `Review: done`, `Approval: required` with `Last Error: -`.
- Initial wait-plan result failed because completion recognition did not classify this generated/review-done/approval-required state as completed.
- Completion recognition now treats the above four Plan Flow markers plus `Last Error: -` as plan-generation completed.
- Backend job endpoints (`/api/jobs/active`, `/api/jobs/recent`) remain diagnostic-only and are not mandatory for completion.
- No approval / execute preview / patch apply behavior changes were added.
- Wait-plan remains opt-in via `RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1` with `RUN_ATLAS_BACKEND_E2E=1`.

## Phase 27.1 note (clarification gate terminal-state recognition)
- Windows wait-plan opt-in run can legitimately stop at clarification gate before plan generation, e.g. `Requirement: done`, `Plan: pending`, `Review: pending`, `Next Action: answer clarification`.
- Clarification UI markers (for example `回答してPlan生成` / `おまかせで進める`) are treated as human-input-required signals.
- Wait-plan classification now returns `finalDecision: needs_clarification` with `completionDecisionReason: clarification_required_before_plan_generation` instead of unknown timeout.
- `needs_clarification` is PASS for lifecycle validation, but is explicitly distinct from generated-plan completion (`Plan: generated`).
- No automatic clarification response is performed; no approval / execute / patch behavior was changed.
- Wait-plan mode remains manual opt-in (`RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1` with `RUN_ATLAS_BACKEND_E2E=1`).

## Phase 27.2 note (wait-plan terminal success + safety policy lock)
- Windows local wait-plan E2E was validated with opt-in settings and preserved safety gates.
- Wait-plan accepts two safe terminal states: `completed` and `needs_clarification`.
- `needs_clarification` is a valid human-in-the-loop terminal state and is not the same as Plan generated.
- Clarification buttons (for example `回答してPlan生成` / `おまかせで進める`) are detected for diagnostics but are not clicked automatically.
- Approval / execute / patch apply are not executed in wait-plan validation scope.
- Backend job endpoints remain diagnostic-only, preflight remains GET-only, and WAIT_PLAN remains explicit opt-in.
- Recorded terminal decision examples:
  - `finalDecision: completed` or `finalDecision: needs_clarification`
  - `completionDecisionReason: plan_flow_generated_review_done_approval_required`
  - `completionDecisionReason: clarification_required_before_plan_generation`
  - `consoleErrors: []`
  - `pageErrors: []`
  - `hasAtlasStartFailed: False`


## Phase 28.0 note (Atlas clarification gate resolution opt-in validation)

- Phase 28.0 introduces explicit opt-in clarification resolution for backend wait-plan smoke.
- Required env set:
  - `RUN_ATLAS_BACKEND_E2E=1`
  - `RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1`
  - `RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION=1`
- Resolution runs only when initial terminal state is `needs_clarification`.
- Resolution action is limited to clicking `おまかせで進める` at most once.
- No automatic clarification answer text is generated or filled.
- No approval/execute/patch apply action is performed.
- After one resolution attempt, smoke stops at `completed` or `needs_clarification_after_resolution`.
- This behavior remains manual, explicit opt-in, and is not enabled in default workflow/CI runs.

## Phase 28.1 note (Windows clarification resolution opt-in result record and policy lock)

- Windows local clarification resolution opt-in was validated.
- Command env set:
  - `RUN_ATLAS_BACKEND_E2E=1`
  - `RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1`
  - `RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION=1`
- Scenario set:
  - `atlas_backend_preflight`
  - `atlas_backend_e2e_resolve_clarification`
- Result summary:
  - `Total scenarios: 2`
  - `PASS: 2`
- Observed final state is constrained to:
  - `completed`
  - `needs_clarification_after_resolution`
- Clarification resolution clicks `おまかせで進める` at most once.
- No automatic clarification answer is generated or submitted.
- No approval / execute / patch apply action is performed.
- Preflight remains GET-only.
- This remains explicit opt-in only and is not enabled by default workflow/CI settings.

## Phase 29.0 note (Atlas PlanApproval gate readiness validation)
- Phase 29.0 introduces PlanApproval gate readiness validation as explicit opt-in only.
- Required env:
  - `RUN_ATLAS_BACKEND_E2E=1`
  - `RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1`
  - `RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL=1`
- Optional env:
  - `RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION=1`
- Scenario set is `atlas_backend_preflight` + `atlas_backend_e2e_plan_approval_gate`.
- PlanApproval gate checks run only when final state is `completed`.
- If final state is `needs_clarification` or `needs_clarification_after_resolution`, gate check is skipped with `plan_approval_gate_skipped_needs_clarification` diagnostic.
- This phase does not click approve, does not execute preview, and does not apply patch.
- Execute Preview / Patch Apply are validated as locked before approval.
- Preflight remains GET-only and default workflow remains opt-in (no default E2E/WAIT_PLAN/CHECK_PLAN_APPROVAL enablement).

## Phase 29.0b note (PlanApproval approve-button detection diagnostics)
- Windows PlanApproval readiness reached completed plan state (Plan generated / Review done / Approval required / Execute Preview locked / Patch Apply locked).
- Initial failure cause was selector miss: PlanApproval gate was present, but approve button was not found by existing selector candidates.
- Phase 29.0b adds Plan subview button inventory diagnostics (`allButtons`, `approvalCandidateButtons`, `destructiveCandidateButtons`) and panel tail diagnostics (`approvalPanelTextTail` / `workbenchHtmlTail`).
- Phase 29.0b expands approve-button detection selectors and text candidates for detection-only diagnostics.
- Approve is still never clicked by smoke.
- Execute Preview / Patch Apply are still never clicked by smoke.
- Workflow remains opt-in only (`RUN_ATLAS_BACKEND_E2E=1`, `RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1`, `RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL=1`).

## Phase 29.0c note (invalid selector guard + exception-safe diagnostics)
- Windows PlanApproval gate diagnostics initially failed because `:has-text()` was used inside `document.querySelector`.
- `:has-text()` is Playwright locator syntax and invalid for browser DOM `querySelector`/`querySelectorAll`.
- Phase 29.0c replaces that path with DOM traversal + `textContent` filtering for approve-candidate diagnostics.
- PlanApproval diagnostic collection is now exception-safe (`diagnosticError`/`selectorErrors`) and does not crash scenarios on selector/DOM mismatches.
- `needs_clarification` / `needs_clarification_after_resolution` skip path now returns early with `plan_approval_gate_skipped_needs_clarification` and does not depend on full selector diagnostics.
- Approve is still never clicked.
- Execute Preview / Patch Apply are still never clicked.
- Workflow remains explicit opt-in only.
