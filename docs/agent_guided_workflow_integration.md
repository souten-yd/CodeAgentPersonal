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
