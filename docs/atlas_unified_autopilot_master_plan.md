# Atlas Unified Autopilot Master Plan

## Purpose

This document fixes the long-term Atlas direction in the repository: Task and Agent must not grow as independent user-facing features. They are unified into Atlas as Planner, Autopilot, Plan Pool, and Nexus Research Pipeline capabilities.

This PR is documentation and contract-test only. It does not change runtime behavior, UI, or API behavior.

## Final Atlas Integration Policy

- **Task = PlanItem**.
  - A Task is not a standalone product surface.
  - A Task is a small work unit inside an Atlas Plan.
  - Future schema and storage work should model this as `AtlasPlanItem` in an `AtlasPlanPool`.
- **Agent = Autopilot**.
  - An Agent is not a separate runner or user-facing feature.
  - The autonomous execution concept belongs to Atlas Autopilot.
- **Planner = Plan Poolを作る**.
  - Planner receives requirements, collects context, asks clarifying questions when needed, plans, reviews, and enqueues PlanItems into the Plan Pool.
- **Autopilot = Plan Poolをpipeline実行する**.
  - Autopilot pulls PlanItems from the Plan Pool in order and executes them through a guarded Pipeline.
- **Nexus = Research Request / Context Pack の文脈収集エンジン**.
  - Nexus is not only Memory search.
  - Nexus handles UI design research, technical research, intent-understanding support, formula and scoring support, log investigation, and other Research Request flows.
  - Nexus returns Context Packs that Planner and Autopilot can consume.
- New additions must be **Atlas内部専用部品** rather than new user-facing features.
- Existing implementations should be reused as Capabilities.
- Do not create a new Task Runner.
- Do not create a new Agent Runner.
- Do not add new Task / Agent API surfaces.
- Integrate through Atlas API instead.

## Current Baseline Assumptions

- The current `AtlasAutopilot` is preview-only; it has no auto approve or auto apply behavior yet.
- Existing `TaskPlanningRunner` already connects Requirement analysis, Clarification, Nexus context, Planner / DeepPlanner, PlanReviewer, and PlanStorage, so it should be reused as the Planner Layer.
- Existing `ImplementationExecutor` already has dry_run / safe_apply, approval gate, patch generation, and verification MVP behavior, so it should be reused as Autopilot Execution Capability.
- Existing `PlanReviewer` already detects destructive changes, large changes, dependency risk, security risk, and DB/API/UI breakage risk, so it should be reused as the Policy Gate.
- The current main branch after restoring the KasaneCore_v3.0 baseline is the source of truth.


## Atlas Journal / Recovery Policy

- JSONを機械可読の正本とする。
- Markdownを人間/LLM向けの共有記録とする。
- events.ndjsonを時系列復元ログとする。
- UIは状態の正本ではなく、Journal / Recoveryから復元した状態を表示する。
- ブラウザリロード後もサーバ側保存状態からCurrent Item / Status / Next Actionを復元する。
- チャットが切れてもcheckpoint.mdを貼れば続きから再開できる。

## Execution Safety Policy

- Initial execution is dry_run-centered.
- low-risk safe_apply is deferred to later PRs and must be introduced gradually.
- `delete` is initially forbidden for automatic execution.
- `run_command` is initially forbidden for automatic execution unless explicitly introduced through a later allowlisted TestCommandRunner path.
- TestCommandRunner uses an allowlist model.
- DebugLoopRunner must always have max retry limits.
- If Nexus returns no context, the flow should continue with a warning rather than fail hard.
- Approval gates must remain explicit at the pool, item, and patch levels until a later PR safely narrows low-risk automation.

## UI Policy

- Atlas UI integration must not create a separate Task or Agent product area.
- The UI must be integrated into Atlas surfaces.
- iPhone Safari must not suffer horizontal layout breakage.
- Any future UI work should favor responsive layouts, wrapping text, scroll-safe containers, and mobile-safe button groups.

## Target Architecture

```text
Atlas UI
  ↓
Atlas API
  ↓
Atlas Orchestrator
  ├─ Planner Service
  │   ├─ Requirement Analyzer
  │   ├─ Clarification Manager
  │   ├─ Nexus Context Builder
  │   ├─ Nexus Research Request
  │   ├─ Planner / DeepPlanner
  │   └─ PlanReviewer
  │
  ├─ Plan Pool Service
  │   ├─ AtlasPlanPool
  │   ├─ AtlasPlanItem
  │   ├─ dependency管理
  │   ├─ status管理
  │   └─ pool approval
  │
  ├─ Autopilot Pipeline Runner
  │   ├─ Policy Gate
  │   ├─ Item approval
  │   ├─ ImplementationExecutor
  │   ├─ VerificationRunner
  │   ├─ TestCommandRunner
  │   ├─ DebugLoopRunner
  │   └─ Patch approval
  │
  └─ Outcome Service
      ├─ final report
      ├─ run log
      ├─ Nexus outcome save
      └─ reusable lesson save
```

## Capability Reuse Map

| Atlas Layer | Reused Capability | Direction |
| --- | --- | --- |
| Planner Service | TaskPlanningRunner | Reuse as Planner Layer instead of creating Task as a standalone feature. |
| Context Collection | Nexus context and research components | Extend as Nexus Research Request / Context Pack engine. |
| Policy Gate | PlanReviewer | Reuse risk detection for Autopilot policy checks. |
| Pipeline Execution | ImplementationExecutor | Reuse dry_run, safe_apply MVP, patch generation, approval gate, and verification capability. |
| Verification | Existing verification hooks | Integrate into VerificationRunner and TestCommandRunner over time. |
| Outcome Persistence | Nexus / plan storage capabilities | Save run logs, outcomes, and reusable lessons through Atlas-internal services. |

## Non-Goals

- No runtime behavior changes in PR-ATLAS-PIPE-0.
- No UI changes in PR-ATLAS-PIPE-0.
- No API changes in PR-ATLAS-PIPE-0.
- No new user-facing Task feature.
- No new user-facing Agent feature.
- No new Task / Agent API.
- No new Task Runner / Agent Runner.
