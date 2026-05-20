# Atlas Autopilot Current Status (PR-ATLAS-PIPE-42B)

## Completed

- PR-ATLAS-PIPE-0〜42
- PR-SEARXNG-SECRET-SYNC-01

## Current

- PR-ATLAS-PIPE-42B

## Next

- PR-ATLAS-PIPE-43: Nexus Context Refresh for implementation/debug/evaluation

## Known Current Code Facts

- PR-42 adds read-only code intelligence tools.
- PR-42B hardens Code Intel tools for large repositories.
- Code Intel supports single-file relative_path, safe per-file read failures, dependency resolution metadata, and safe related test verification hints.
- PR-42B does not add arbitrary command execution, remote git operations, auto rollback, or Task/Agent APIs.

## Compatibility Markers
- PR-ATLAS-PIPE-0〜41
- PR-ATLAS-PIPE-41B
- PR-ATLAS-PIPE-42

## PR-ATLAS-PIPE-43 Context Refresh
- Adds bounded local-first Nexus Context Refresh bundles.
- Web/Deep Research require explicit manual policy and budget.
- No side effects: no safe_apply/verification/debug/patch/restore/rollback.
- Next: PR-ATLAS-PIPE-44 LLM Evaluator uses context bundle + diff/tests.


- PR-ATLAS-PIPE-43B hardens Context Refresh before LLM Evaluator: Nexus sources in bundle, changed_files metadata resolution, audit events, collector partial failure, and bundle API path-traversal safety.
\n## PR-ATLAS-PIPE-44B\n- Hardened evaluator: path safety, input packet resolution, diff_summary extraction, prompt contract, strict policy validation, no-side-effect guarantees.\n- Evaluator remains decision-only; PR-45 consumes evaluator results for multi-item guarded autopilot.


## PR-ATLAS-PIPE-44C
- Restores evaluator audit events and markdown persistence before multi-item autopilot.
- Evaluator results are saved as json and md.
- Evaluator emits evaluator_started/evaluator_completed/evaluator_fallback_used/evaluator_policy_override/evaluator_blocked/evaluator_failed.
- Evaluator remains decision-only and side-effect-free.
- Next: PR-ATLAS-PIPE-45 Multi-item guarded autopilot consumes evaluator results and audit events.


## PR-ATLAS-PIPE-46
- Adds bounded retry loop for verification failures (verification rerun only).
- Retryable: transient/environment/blocked/skipped; non-retryable: deterministic code/test failures.
- Safety: no safe_apply rerun, no rollback/restore/debug review/patch regeneration.
- Multi-item integration is opt-in (`include_bounded_retry=false` by default).
- Next PR: PR-ATLAS-PIPE-47 supervised patch regeneration.

## PR-ATLAS-PIPE-46B
- Retryable transient verification failures can continue through max attempts with per-attempt reclassification.
- Multi-item bounded-retry recovered results normalize `verification_result.status` to `passed` with recovery metadata.
- Next PR: PR-ATLAS-PIPE-47 supervised patch regeneration with manual approval gate.

- PR-ATLAS-PIPE-47B hardens supervised patch regeneration (audit events, prompt contract, evidence loading, target validation, manual approval only).

- PR-ATLAS-PIPE-48: Added manual approval gate for regenerated patch candidates; approved candidates now create safe_apply handoff artifacts only (no apply/verification/retry/rollback/restore/debug/autopilot resume). Next: PR-ATLAS-PIPE-49 supervised safe_apply execution from approved handoff.

- PR-ATLAS-PIPE-49: supervised safe_apply from approved handoff; requires approved handoff/hash/gate recheck; supports dry_run; safe_apply only; no verification/retry/rollback/restore. Next: PR-ATLAS-PIPE-50 supervised verification after handoff safe_apply.
- PR-ATLAS-PIPE-49B: Hardened supervised handoff safe_apply (atomic restore on failure, result history metadata, dry_run invalid=>blocked, audit event completeness). Next: PR-ATLAS-PIPE-50 supervised verification after safe_apply result evaluation.

- PR-ATLAS-PIPE-50: supervised handoff verification after applied safe_apply (allowlisted verification + local-only context refresh + evaluator, no rerun/retry/rollback/restore/debug/regen).


- Completed PRs: PR-ATLAS-PIPE-0〜51, PR-ATLAS-UI-FIX-50A, PR-SEARXNG-SECRET-SYNC-01
- Current PR: PR-ATLAS-PIPE-51B
- Next PR: PR-ATLAS-PIPE-52: Close supervised loop by routing exhausted/not-retryable verification failures to patch regeneration recommendation

## PR-ATLAS-PIPE-53 Current Status
- PR-53 manually executes supervised patch regeneration from saved recommendation payloads.
- PR-53 only creates patch candidates from `recommendation_ready` results.
- PR-53 does not approve, apply, verify, retry, rollback, restore, run DebugReview, use remote git, or continue multi-item autopilot.
- Generated candidates remain manual approval required with `safe_apply_ready=false`.
- Current PR: PR-ATLAS-PIPE-53
- Next PR: PR-ATLAS-PIPE-54: Finalize supervised item status transitions from loop outcomes

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


## PR-ATLAS-PIPE-59 Operator Loop UI
- Added UI-only operator loop over existing APIs: prepare -> dry_run -> execute one action -> refresh -> next step.
- Execute requires dry_run first and confirmation token/text (EXECUTE ONE ACTION).
- No auto continue, no execute all, no rollback/restore/debug/remote git, and no backend execution semantics added.
- Current PR: PR-ATLAS-PIPE-59
- Next PR: PR-ATLAS-PIPE-60: Guarded semi-automatic operator loop with per-step confirmation


## PR-ATLAS-PIPE-59C update
- Hardened Manual Executor / Post Refresh CA_DATA root resolution via request-aware resolved root.
- Manual Executor persistence now writes final metadata before JSON/MD persistence.
- Root consistency is required before semi-auto; this PR adds no semi-auto or auto-continue behavior.


- PR-ATLAS-PIPE-60B hardens guarded semi-auto loop (UI binding, dry_run_next_action, policy flags, real tests).
- no full autonomous agent / no execute all / no auto continue / no follow-up execution after refresh.

- PR-ATLAS-PIPE-60C fixes dry_run_next_action token construction.
- Non-executable next actions are pre-blocked before Manual Executor.
- manual_review / investigate_failure / none cannot enter executor path.
- no execute all / no auto continue remains enforced.

- PR-ATLAS-PIPE-60D completes CA_DATA root propagation for MultiStatus and NextActionOrchestrator.
- GuardedLoop / MultiStatus / Orchestrator / ManualExecutor / PostRefresh now use the same resolved root.
- Path("ca_data") direct usage is prohibited in these stacks.
- This PR does not add execute-all or auto-continue.
- PR-61 can now focus on persistent repo symbol index and dependency graph.


- PR-ATLAS-SCALE-61: Persistent repo symbol index and incremental dependency graph (no execution semantics changes).
- Next PR: PR-ATLAS-SCALE-62 for PlanPool scope/context refresh integration.
