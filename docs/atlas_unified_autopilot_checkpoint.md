# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Current Architecture Decision

- Task独立機能は廃止する。
- TaskはPlanItemとして扱う。
- Agent独立機能は廃止する。
- AgentはAutopilotとして扱う。
- PlannerはPlan Poolを作る。
- AutopilotはPlan Poolを順次実行する。
- Nexusは文脈収集・Research Requestの実行基盤として使う。
- 新規ユーザー向け機能は増やさず、Atlas内部専用部品として追加する。

## Completed PRs

- PR-ATLAS-PIPE-0: completed
- PR-ATLAS-PIPE-1: completed
- PR-ATLAS-PIPE-2: completed
- PR-ATLAS-PIPE-3: completed
- PR-ATLAS-PIPE-4: completed

## Current PR

PR-ATLAS-PIPE-5

## Next PR

PR-ATLAS-PIPE-6: Approval Gate

## Important Constraints

- v3.0復元後のmainを正とする。
- Task / Agent APIを新規に増やさない。
- 既存Requirement / Planner / PlanReviewer / ImplementationExecutorを流用する。
- delete / run_command は初期段階では自動実行禁止。
- Nexusが空でも処理継続。
- iPhone SafariでUIを崩さない。
- 既存 Lumen / Echo / Nexus を壊さない。
- runtime / UI / API はこのPRでは変更しない。

## Known Current Code Facts

- AtlasAutopilot is preview-only.
- TaskPlanningRunner already connects Requirement, Nexus context, Planner, DeepPlanner, PlanReviewer, PlanStorage.
- ImplementationExecutor has dry_run / safe_apply MVP.
- PlanReviewer has risk detection.
- Current main includes Restore KasaneCore_v3.0 baseline.
- PR-ATLAS-PIPE-1 adds schema only and does not add runtime/storage/API/UI behavior.
- PR-ATLAS-PIPE-2 adds PlanPool storage only and does not add runtime/API/UI behavior.
- PR-ATLAS-PIPE-3 adds a pure mapper from existing planner/autopilot plan payloads to AtlasPlanPool and does not add runtime/storage/API/UI behavior.
- PR-ATLAS-PIPE-4 adds Autopilot Policy Gate schema/service only and does not add runtime/storage/API/UI behavior.
- PR-ATLAS-PIPE-5 adds a dry_run-only Pipeline Runner and does not add safe_apply/API/UI behavior.

## Open Questions

- UI統合はv3.0 ui.htmlに直接追加するか、再度web/js分割を先に戻すか。
- Nexus Research Adapterは既存Nexus APIのどこまで直接使うか。
- TestCommandRunnerの初期allowlistをどこまで広げるか。

## Next Instruction

PR-ATLAS-PIPE-6を実装する。
Pool / Item / Patch のApproval Gateを明示し、approvalなしでは適用処理へ進まない状態モデルを追加する。
