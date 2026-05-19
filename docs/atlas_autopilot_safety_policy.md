# Atlas Autopilot Safety Policy (PR-ATLAS-PIPE-41B)

## Local Mode

- 認証なしで可能
- local repo inspection
- safe_apply
- snapshot
- restore
- verification
- dev tools

## GitHub Connected Mode

- 認証がある場合のみ
- clone/fetch/pull/push/PR/Actions 取得
- token をログに出さない
- token を docs/ca_data に保存しない
- GitHub auth is only needed for remote operations

## Forbidden

- no arbitrary command execution
- shell=True
- delete/run_command auto execution
- remote git operations from read-only tools
- auto rollback 現時点では禁止
- /api/task/* /api/agent/* 追加禁止

## Required

- project_path
- path validation
- snapshot before apply
- command allowlist
- bounded max files/bytes
- audit events

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
- Bounded retry remains verification-rerun only and forbids safe_apply rerun, rollback, restore, debug review, and patch regeneration.
- Runtime budget and changed-file drift are enforced during retries.

- PR-ATLAS-PIPE-47B hardens supervised patch regeneration (audit events, prompt contract, evidence loading, target validation, manual approval only).

- PR-ATLAS-PIPE-48: Added manual approval gate for regenerated patch candidates; approved candidates now create safe_apply handoff artifacts only (no apply/verification/retry/rollback/restore/debug/autopilot resume). Next: PR-ATLAS-PIPE-49 supervised safe_apply execution from approved handoff.

- PR-ATLAS-PIPE-49: supervised safe_apply from approved handoff; requires approved handoff/hash/gate recheck; supports dry_run; safe_apply only; no verification/retry/rollback/restore. Next: PR-ATLAS-PIPE-50 supervised verification after handoff safe_apply.
- PR-ATLAS-PIPE-49B: Hardened supervised handoff safe_apply execution safety (atomic temp-item handling + restoration guarantees), blocked dry_run semantics, metadata/audit completeness; verification/retry/rollback/restore/debug/patch-regeneration remain disabled.

- PR-ATLAS-PIPE-50: supervised handoff verification after applied safe_apply (allowlisted verification + local-only context refresh + evaluator, no rerun/retry/rollback/restore/debug/regen).


- Completed PRs: PR-ATLAS-PIPE-0〜51, PR-ATLAS-UI-FIX-50A, PR-SEARXNG-SECRET-SYNC-01
- Current PR: PR-ATLAS-PIPE-51B
- Next PR: PR-ATLAS-PIPE-52: Close supervised loop by routing exhausted/not-retryable verification failures to patch regeneration recommendation

## PR-ATLAS-PIPE-53 Safety Policy
- Patch Regen From Recommendation is manual-trigger only and accepts only saved `recommendation_ready` payloads.
- It generates a supervised patch candidate only; manual approval remains required before any later safe_apply flow.
- It enforces no safe_apply, no verification, no bounded retry, no rollback, no restore, no DebugReview, no remote git, and no multi-item autopilot resume.
- Dry run is validation-only and must not execute patch regeneration.
- Generated candidates must remain `approval_status=pending` and `safe_apply_ready=false`.

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
