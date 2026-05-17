- manual loop through safe_apply candidateをPR-33で固定
- 実機テスト前にPR-34でfinal smoke/checklist
- 自動実行はまだ開始しない

# Atlas Unified Autopilot Master Plan

## Current Delivery Status (PR-ATLAS-PIPE-33)

- approved Patch Proposal → PlanItem draft → Approval Gate → manual safe_apply → manual verification → manual DebugReview → manual Patch Proposal まで固定済み。
- Patch Proposal generation remains manual only.
- Patch Proposal Approvalは引き続き手動。
- approved Patch Proposal → PlanItem draft → Approval Gate → manual safe_apply → manual verification → manual DebugReview → manual Patch Proposal → manual Patch Proposal approval までをPR-31で固定。
- PlanItem Draft作成は引き続き手動。
- 次はapproved Patch Proposal → manual PlanItem Draft UX/E2E。
- PR-ATLAS-PIPE-30Bはdocs/continuation/test polishのみで新規実行系は追加しない。


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
- API integration must stay under `/api/atlas/*`: PlanPool creation/retrieval, Pipeline dry_run/status, and Recovery summaries are Atlas capabilities, not new Task or Agent APIs.
- Atlas API dry_run integration must not automatically execute safe_apply, TestCommandRunner, DebugLoopRunner, external Web research, or Deep Research jobs.

## Current Baseline Assumptions

- The current `AtlasAutopilot` is preview-only; it has no auto approve or auto apply behavior yet.
- Existing `TaskPlanningRunner` already connects Requirement analysis, Clarification, Nexus context, Planner / DeepPlanner, PlanReviewer, and PlanStorage, so it should be reused as the Planner Layer.
- Existing `ImplementationExecutor` already has dry_run / safe_apply, approval gate, patch generation, and verification MVP behavior, so it should be reused as Autopilot Execution Capability.
- Existing `PlanReviewer` already detects destructive changes, large changes, dependency risk, security risk, and DB/API/UI breakage risk, so it should be reused as the Policy Gate.
- The current main branch after restoring the KasaneCore_v3.0 baseline is the source of truth.



## Nexus Research Policy

- Nexus Research RequestはPlanner/Autopilotが不足文脈を取得するための内部要求である。
- ContextPackはPlanner/Autopilotへ渡す構造化文脈である。
- Nexus未接続、空、失敗時もAtlasは停止せず、warning付きContextPackで継続する。
- UIデザイン調査、技術仕様調査、意図理解補助、数式/スコアリング補助、ログ調査などを将来扱う。

## Research Item Execution Policy

- PlanPool内のresearch itemは、実装itemとは別扱いにする。
- research itemはNexus Research Adapterを呼び、ContextPackを生成する。
- ContextPackはPlanner / Autopilotの判断材料としてJournalに保存する。
- Nexus未接続や失敗時もwarning付きContextPackで継続する。

## Outcome Persistence Policy

- Atlasは成功・失敗・debug lesson・research context・verification/safe_apply結果をOutcomeとして記録する。
- OutcomeはJournalへJSON/Markdownで保存し、可能ならNexusへ保存する。
- Nexus未接続や保存失敗時もAtlas flowを止めない。
- Outcomeは将来のPlanner/Nexus Context Builderが再利用する。

## Atlas Journal / Recovery Policy

- JSONを機械可読の正本とする。
- Markdownを人間/LLM向けの共有記録とする。
- events.ndjsonを時系列復元ログとする。
- UIは状態の正本ではなく、Journal / Recoveryから復元した状態を表示する。
- ブラウザリロード後もサーバ側保存状態からCurrent Item / Status / Next Actionを復元する。
- チャットが切れてもcheckpoint.mdを貼れば続きから再開できる。

## DebugLoop Policy

- DebugLoopRunnerは失敗ログを読み、原因要約・最小修正方針・再試行可否を判断する。
- DebugLoopRunnerは最初は分析/計画のみで、patch生成や適用は行わない。
- 実行履歴はAtlasJournalへdebug_notes.md/events.ndjsonとして保存する。
- max retryを超えたら停止し、ユーザー確認または再計画へ回す。

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
- PR-ATLAS-PIPE-14 redesigns Atlas as an Atlas Dashboard instead of preserving the old complex UI layout.
- The redesigned Atlas UI should be simple, graphical, and card-centered: Goal Composer, PlanPool cards, Pipeline progress, Current Item, Recovery, and Details drawer.
- Detailed settings, raw JSON, Markdown, and event logs should be shown only when needed through collapsed details panels.
- Browser reload should restore state from Recovery/latest plus the persisted last pool/run identifiers.
- Chat continuation / handoff is an Atlas Dashboard Details capability, not a separate Task or Agent surface.
- Chat Continuation / handoff was implemented in PR-ATLAS-PIPE-15.
- A user can paste the Dashboard-generated Continuation Prompt into a new chat to resume from the latest Atlas Journal / Recovery / checkpoint state.
- Continuation summaries should include the current goal, pool/run IDs, pipeline status, progress counts, last event, next action, checkpoint path, PlanPool Markdown path, pipeline state path, and events.ndjson path.
- The initial Dashboard surface remains dry-run only and must not expose safe_apply, TestCommandRunner, DebugLoopRunner, external Web research, or Deep Research execution controls.
- The next major Atlas planning task is moving Create Plan from fallback PlanPool-only behavior to a real planner bridge backed by existing Planner / DeepPlanner / Requirement Analyzer results.



## Real Planner Bridge Direction

Atlas Create Plan should move from fallback PlanPool-only behavior to a bridge that can reuse the existing TaskPlanningRunner planning stack. When an application-provided LLM JSON function is available, Atlas PlanPool creation may run Requirement analysis, Nexus context building, Planner / DeepPlanner, and PlanReviewer, then convert the planner result into PlanItems. If the planner is unavailable, asks for clarification, or fails, Atlas must not block the dashboard flow: unavailable or failed planner runs fall back to a warning-bearing fallback PlanPool, while clarification waits are returned as non-fatal Details/JSON state. This bridge remains planning-only and does not execute safe_apply, TestCommandRunner, DebugLoopRunner, or DeepResearch work.

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


## Orchestration Summary Policy

Atlas API, Dashboard, Continuation, Recovery, and Journal checkpoint surfaces should share one orchestration summary vocabulary for phase, severity, next_action, and gate booleans. The summary keeps UI behavior consistent for not_started, plan_ready, clarification_required, approval_required, stale_recovery, running, completed, failed, and blocked states.

- API responses may include `orchestration_summary` as an additive, backward-compatible helper.
- Dashboard Next Action and dry-run/refresh button state should prefer `orchestration_summary` when present and fall back to legacy state derivation when absent.
- Continuation prompts should include planner_mode, planner_status, used_fallback, fallback_reason, clarification/approval/stale gates, questions count, and the orchestration next_action.
- Journal checkpoint next_action text should stay aligned with the same state-specific wording so Markdown recovery and UI recovery tell users the same next step.
- This policy does not authorize safe_apply, TestCommandRunner, DebugLoopRunner, DeepResearch/Web execution, arbitrary command execution, or new Task/Agent APIs.


- PR-ATLAS-PIPE-18: AtlasPlannerBridge llm_json_fn を既存モデル/OpenAI互換 backend へ配線。backend unavailable/timeout/invalid JSON時はfallback継続。

- Next PR: PR-ATLAS-PIPE-21: Safe apply execution gate / manual approval UI

## Planner Backend Wiring Status

- PR-ATLAS-PIPE-18でLLM JSON adapter wiringは実装済み。
- real Plannerが使える条件:
  - `app.state.atlas_llm_json_fn` がcallable。
  - または既存state/envからOpenAI互換backend base_urlが解決できる。
- backend unavailable / timeout / raise / invalid JSON時はfallback PlanPoolへ戻る。
- PR-ATLAS-PIPE-19でclarification answer flowは実装済み。
- 次の課題はapproval_required itemをAtlas Dashboard / API / Continuationで扱うこと。
- approvalを記録しても、safe_apply自動実行はまだ別PRで扱う。

- PR-ATLAS-PIPE-19 adds clarification answer flow for waiting_for_clarification.
- Clarification answers are merged into Planner input / Requirement context and can trigger re-planning.
- PR-ATLAS-PIPE-19 does not execute safe_apply/TestCommand/DebugLoop/DeepResearch.


## Current Sequencing Note

- PR-ATLAS-PIPE-19でClarification answer flowは実装済み。
- 次の課題はapproval_required itemをAtlas Dashboard / API / Continuationで扱うこと。
- approvalを記録しても、safe_apply自動実行はまだ別PRで扱う。

- PR-ATLAS-PIPE-20: approval-aware API/UI/Journal preparation (record-only, no safe_apply execution).


## Approval Gate status update

- Approval GateはPR-20で記録/可視化まで実装済み。
- PR-20Bでpending count/表示整合を修正。
- safe_apply実行はPR-21以降。


- PR-ATLAS-PIPE-21: completed.
- PR-ATLAS-PIPE-21B: current (manual safe_apply UI eligibility/candidate listing/tests fixes).
- PR-ATLAS-PIPE-22: next (post-apply verification manual gate).


- manual safe_apply gateはPR-21〜21Cで安定化
- post-apply verificationはPR-22


- executor未接続ではnormal safe_applyをblockedにする
- dry_runのみsimulated可能
- post-apply verificationはPR-22


## Patch Proposal Policy

- Patch Proposalは提案レビューのみ。
- 実適用はまだ禁止。
- 次はPatch Proposal approval gate。

- Patch Proposal approvalは記録のみ
- 実適用はまだ禁止
- 次はapproved proposalをsafe_apply PlanItem draftへ変換

- approved/rejected proposalは再生成で上書きしない
- needs_revision時のみrevision proposalを許可するか、別フローにする
- approved proposalはPlanItem draftへ変換
- draftはapproval_required
- 実適用は既存manual approval + manual safe_apply gateに委ねる
- 自動実行はまだ禁止
- approved Patch Proposal → PlanItem draft → Approval Gate → manual safe_apply candidate までをPR-26Bで固定
- 実行は引き続き手動
- 次はapproved draft PlanItemのmanual safe_apply UX/E2E


- approved Patch Proposal → manual PlanItem draft creation までをPR-32で固定
- PlanItem approvalは引き続き手動
- 次はgenerated draft → manual PlanItem approval UX/E2E
