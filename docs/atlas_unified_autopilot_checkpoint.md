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
- PR-ATLAS-PIPE-5: completed
- PR-ATLAS-PIPE-6: completed
- PR-ATLAS-PIPE-7: completed
- PR-ATLAS-PIPE-8: completed
- PR-ATLAS-PIPE-8B: completed
- PR-ATLAS-PIPE-9: completed
- PR-ATLAS-PIPE-10: completed
- PR-ATLAS-PIPE-11: completed
- PR-ATLAS-PIPE-12: completed
- PR-ATLAS-PIPE-13: completed
- PR-ATLAS-PIPE-14: completed
- PR-ATLAS-PIPE-14B: completed
- PR-ATLAS-PIPE-14C: completed
- PR-ATLAS-PIPE-15: completed
- PR-ATLAS-PIPE-15B: completed
- PR-ATLAS-PIPE-16: completed
- PR-ATLAS-PIPE-17: completed
- PR-ATLAS-PIPE-18: completed
- PR-ATLAS-PIPE-18B: completed
- PR-ATLAS-PIPE-19: completed
- PR-ATLAS-PIPE-20: completed
- PR-ATLAS-PIPE-20B: completed

## Current PR

PR-ATLAS-PIPE-20B

## Next PR

PR-ATLAS-PIPE-21: Safe apply execution gate / manual approval UI

## Important Constraints

- v3.0復元後のmainを正とする。
- Task / Agent APIを新規に増やさない。
- 既存Requirement / Planner / PlanReviewer / ImplementationExecutorを流用する。
- delete / run_command は初期段階では自動実行禁止。
- Nexusが空でも処理継続。
- iPhone SafariでUIを崩さない。
- 既存 Lumen / Echo / Nexus を壊さない。
- 初期UIではdry-runのみを表示し、safe_apply/TestCommand/DebugLoop/DeepResearch実行UIは追加しない。

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
- PR-ATLAS-PIPE-6 adds Approval Gate records/service only and does not add safe_apply/API/UI behavior.
- PR-ATLAS-PIPE-7 adds guarded low-risk safe_apply adapter only and does not add API/UI behavior.
- PR-ATLAS-PIPE-8 adds allowlisted TestCommandRunner only and does not add API/UI behavior.
- PR-ATLAS-PIPE-8B adds Atlas Journal / Recovery checkpoint foundation only and does not add API/UI behavior.
- PR-ATLAS-PIPE-9 adds DebugLoopRunner analysis/planning only and does not add automatic patch generation, safe_apply execution, TestCommand execution, API, or UI behavior.
- PR-ATLAS-PIPE-10 adds Nexus ResearchRequest / ContextPack schema and adapter only and does not add API/UI behavior.
- PR-ATLAS-PIPE-11 lets Pipeline Runner execute item_type=research through AtlasNexusResearchAdapter.
- PR-ATLAS-PIPE-12 adds Nexus Outcome Writer schema/service only and does not add API/UI behavior.
- PR-ATLAS-PIPE-13 adds minimal Atlas API integration for PlanPool creation, PlanPool retrieval, Pipeline dry_run, status, and recovery.
- PR-ATLAS-PIPE-13 does not add Task/Agent APIs, safe_apply execution, test execution, DebugLoop execution, external Web access, or Deep Research jobs.
- PR-ATLAS-PIPE-14 adds a redesigned Atlas Dashboard UI for PlanPool, Pipeline dry-run status, and Recovery.
- PR-ATLAS-PIPE-14 intentionally does not preserve the old complex Atlas UI layout.
- Advanced settings are hidden by default.
- PR-ATLAS-PIPE-14 does not add safe_apply/TestCommand/DebugLoop/DeepResearch execution controls.
- PR-ATLAS-PIPE-14B fixes Atlas Dashboard visual design and static asset loading.
- PR-ATLAS-PIPE-14B adds cache busting/static asset checks so the redesigned UI styles are actually applied.
- PR-ATLAS-PIPE-14B does not add safe_apply/TestCommand/DebugLoop/DeepResearch execution controls.
- PR-ATLAS-PIPE-14C treats missing pipeline state after Recovery as stale recovery warning, not a fatal dashboard error.
- PR-ATLAS-PIPE-15 adds continuation handoff service/API/UI polish.
- Atlas Dashboard can generate a copyable continuation prompt for new chats.
- Continuation uses AtlasJournal / Recovery / Markdown paths and does not execute safe_apply/TestCommand/DebugLoop/DeepResearch.
- PR-ATLAS-PIPE-16 connects Atlas PlanPool creation to existing TaskPlanningRunner / Requirement / Planner / DeepPlanner / PlanReviewer when an LLM JSON function is available.
- PR-ATLAS-PIPE-16 falls back to fallback PlanPool when real planner is unavailable or fails.
- PR-ATLAS-PIPE-16 does not execute safe_apply/TestCommand/DebugLoop/DeepResearch and does not add Task/Agent APIs.
- PR-ATLAS-PIPE-17 adds Atlas orchestration summary for consistent next_action / gate handling.
- PR-ATLAS-PIPE-17 improves waiting_for_clarification / approval_required / stale / completed / failed state handling in API and Dashboard.
- PR-ATLAS-PIPE-17 does not add safe_apply/TestCommand/DebugLoop/DeepResearch execution controls.
- PR-ATLAS-PIPE-18 wires AtlasPlannerBridge llm_json_fn to an OpenAI-compatible/local model backend through AtlasLLMJsonAdapter.
- PR-ATLAS-PIPE-18 registers app.state.atlas_llm_json_fn only when no callable is already present.
- PR-ATLAS-PIPE-18 keeps fallback PlanPool behavior when the backend is unavailable, times out, raises, or returns invalid JSON.
- PR-ATLAS-PIPE-18 does not add safe_apply/TestCommand/DebugLoop/DeepResearch execution controls.
- PR-ATLAS-PIPE-19 adds clarification answer flow for waiting_for_clarification.
- Clarification answers are stored in AtlasClarificationSession and can be merged into Planner input / Requirement context.
- Atlas Dashboard can show Planner questions in Details and submit answers or use assumptions.
- POST /api/atlas/clarifications/answer can re-run planning and return a PlanPool, another waiting_for_clarification response, or fallback PlanPool.
- PR-ATLAS-PIPE-19 does not execute safe_apply/TestCommand/DebugLoop/DeepResearch and does not add Task/Agent APIs.
- Outcome Writer can save success/failure/debug/research/safe_apply/pipeline outcomes to AtlasJournal and optionally to a Nexus client.
- Research item execution does not start external Web access or Deep Research jobs.
- Research item execution does not call ImplementationExecutor, safe_apply, or TestCommandRunner.
- Nexus unavailable/empty/errors must not stop Atlas planning or pipeline flows.
- DebugLoopRunner can write debug_notes.md and debug_attempt_recorded events through AtlasJournal.
- Atlas Journal stores JSON state, Markdown summaries, and events.ndjson for reload/chat recovery.
- TestCommandRunner uses shell=False and rejects non-allowlisted commands.
- delete/run_command remain forbidden.

## Open Questions

- UI統合はv3.0 ui.htmlに直接追加するか、再度web/js分割を先に戻すか。
- Nexus Research Adapterは既存Nexus APIのどこまで直接使うか。
- TestCommandRunnerの初期allowlistをどこまで広げるか。

## Next Instruction

PR-ATLAS-PIPE-21を実装する。
manual approval済みPlanItemに限定して、safe_apply execution gateをUI/APIに追加する。ただし一括自動実行や高リスク自動実行はしない。
- safe_apply自動実行禁止。
- TestCommand自動実行禁止。
- DebugLoop自動実行禁止。
- DeepResearch/Web job起動禁止。
- Task/Agent API追加禁止。
- 任意コマンド実行追加禁止。
- 既存Lumen / Echo / Nexus破壊禁止。

- PR-ATLAS-PIPE-20: approval-aware API/UI/Journal preparation (record-only, no safe_apply execution).
- PR-ATLAS-PIPE-20 adds approval-aware API/UI/Journal preparation for approval_required PlanItems.
- Approval decisions can be recorded for PlanItems and reflected in PlanPool metadata/status.
- Approval records are saved to AtlasJournal and shown in Dashboard Details.
- PR-ATLAS-PIPE-20 does not execute safe_apply/TestCommand/DebugLoop/DeepResearch.
- PR-ATLAS-PIPE-20B fixes approval pending_count and dashboard approval refresh duplication.


## Current PR
- PR-ATLAS-PIPE-21B

## Next PR
- PR-ATLAS-PIPE-22: Verification runner manual gate / post-apply validation

## Known Current Code Facts (update)
- PR-ATLAS-PIPE-21 adds manual safe_apply execution gate for approved low-risk PlanItems.
- safe_apply execution is item-level only and never batch/full-autopilot.
- delete/run_command and medium/high/critical risk items remain blocked.
- PR-ATLAS-PIPE-21 does not auto-run TestCommandRunner/DebugLoopRunner/DeepResearch.
- PR-ATLAS-PIPE-21B fixes manual safe_apply UI eligibility, candidate listing, tests, and checkpoint consistency.

## Next Instruction
- Implement PR-ATLAS-PIPE-22 (manual post-apply verification gate).
