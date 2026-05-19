# Atlas Autopilot Scale Master Plan (PR-ATLAS-PIPE-41B)

## Current Completed Baseline

- PR-40: auto verification failure stop + manual restore suggestion
- PR-41: Dev Tooling Pack 1 read-only local repo inspection tools
- PR-SEARXNG-SECRET-SYNC-01: Windows SearXNG secret_key sync fix

## Goal

- 中〜大規模プロジェクトの guarded autopilot
- local-first
- GitHub optional
- 認証なしでも local repo で修正/検証/restore 可能
- GitHub auth is only needed for remote operations (clone/pull/push/PR/Actions 取得)

## Roadmap

- PR-41B: design docs reconciliation
- PR-42: Dev Tooling Pack 2 - symbol index, dependency graph, related tests
- PR-43: Nexus Context Refresh for implementation/debug/evaluation
- PR-44: LLM Evaluator using diff/tests/dev tools/Nexus context
- PR-45: multi-item guarded autopilot
- PR-46: bounded retry loop
- PR-47: supervised patch regeneration
- PR-48: large project module graph / impact analysis
- PR-49: optional GitHub remote integration
- PR-50: Autopilot dashboard / run recovery


### PR-42 Update
- `symbol_index`, `dependency_graph`, `related_tests` are local-first and GitHub optional.
- GitHub auth is only needed for remote operations.
- Next milestone: PR-43 Nexus Context Refresh for implementation/debug/evaluation.

## PR-ATLAS-PIPE-43 Context Refresh
- Adds bounded local-first Nexus Context Refresh bundles.
- Web/Deep Research require explicit manual policy and budget.
- No side effects: no safe_apply/verification/debug/patch/restore/rollback.
- Next: PR-ATLAS-PIPE-44 LLM Evaluator uses context bundle + diff/tests.


- PR-ATLAS-PIPE-43B hardens Context Refresh before LLM Evaluator: Nexus sources in bundle, changed_files metadata resolution, audit events, collector partial failure, and bundle API path-traversal safety.


## PR-ATLAS-PIPE-45
- Added guarded multi-item autopilot (low-risk approved items only) with strict budget controls: max_items/max_runtime/max_failures/max_changed_files_total.
- Per-item chain: Context Refresh -> auto safe_apply -> auto verification -> failure stop suggestion (if failed) -> Evaluator decision.
- Stop on verification failure, evaluator stop/manual_required/revise, blocked safe_apply/context/evaluator, or budget exhaustion.
- No auto rollback/restore/debug review/patch regeneration.
- Persist run result JSON/MD at ca_data/atlas/multi_item_autopilot/{pool_id}/{auto_id}.(json|md).
- Next PR: PR-ATLAS-PIPE-46 bounded retry loop (without auto rollback).


## PR-ATLAS-PIPE-47 Supervised patch regeneration
- deterministic/code failure after bounded retry can generate a patch proposal candidate only.
- Manual approval required. No auto apply, no verification, no retry execution, no rollback/restore/debug.
- Candidate is saved and attached to item metadata.
- Next PR: PR-ATLAS-PIPE-48 approval gate for regenerated patch candidates and supervised safe_apply handoff.

- PR-ATLAS-PIPE-48: Added manual approval gate for regenerated patch candidates; approved candidates now create safe_apply handoff artifacts only (no apply/verification/retry/rollback/restore/debug/autopilot resume). Next: PR-ATLAS-PIPE-49 supervised safe_apply execution from approved handoff.

- PR-ATLAS-PIPE-49: supervised safe_apply from approved handoff; requires approved handoff/hash/gate recheck; supports dry_run; safe_apply only; no verification/retry/rollback/restore. Next: PR-ATLAS-PIPE-50 supervised verification after handoff safe_apply.

- PR-ATLAS-PIPE-50: supervised handoff verification after applied safe_apply (allowlisted verification + local-only context refresh + evaluator, no rerun/retry/rollback/restore/debug/regen).


- PR-ATLAS-PIPE-52: Patch regen recommendation payload for exhausted/not_retryable supervised retry outcomes (recommendation only; no execution).

## PR-ATLAS-PIPE-53 Patch Regen From Recommendation
- `recommendation_ready` Patch Regen Recommendation results can now be manually triggered to create a supervised patch regeneration candidate.
- PR-53 only creates patch candidates from saved `recommended_payload` data; manual approval is still required.
- Safety remains explicit: no safe_apply / no verification / no retry / no rollback / no restore / no DebugReview / no remote git / no multi-item autopilot resume.
- Generated candidates keep `approval_required=true`, `approval_status=pending`, and `safe_apply_ready=false`.
- Next PR: PR-ATLAS-PIPE-54 finalizes supervised item status transitions from loop outcomes.

## PR-ATLAS-PIPE-54
- Finalizes PlanItem supervised status from loop artifacts.
- Calculates next_action but does not execute next_action.
- No safe_apply/verification/retry/patch regen/approval execution.
- Completes single-item supervised loop state tracking.
- Next PR: PR-ATLAS-PIPE-55 integrate supervised status into multi-item guarded autopilot.



## PR-ATLAS-PIPE-56
- Next Action Orchestrator added: reads multi-item supervised status queues, selects one next action, builds a normalized action contract, and saves JSON/Markdown artifacts.
- It does not execute next actions; manual confirmation remains required.
- No apply/verify/retry/approval/patch-regeneration/rollback/restore/debug-review/remote-git/autopilot-auto-continue actions are executed.
- Current PR: PR-ATLAS-PIPE-57B. Next PR: PR-ATLAS-PIPE-58: Refresh status queue after manual execution and recommend next manual step.
\n- PR-ATLAS-PIPE-58: Post Manual Execution Refresh reads manual executor result, refreshes supervised item status, rebuilds multi-item queue, prepares next manual action contract only (no execute/auto-continue).
