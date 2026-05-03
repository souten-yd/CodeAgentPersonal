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
