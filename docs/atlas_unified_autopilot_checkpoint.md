# Atlas Unified Autopilot Continuation Checkpoint

## Completed PRs

- PR-ATLAS-PIPE-0〜42: completed
- PR-SEARXNG-SECRET-SYNC-01: completed

## Current PR

- PR-ATLAS-PIPE-42B

## Next PR

- PR-ATLAS-PIPE-43: Nexus Context Refresh for implementation/debug/evaluation

## Important Constraints

- 任意コマンド実行は禁止。
- shell=Trueは禁止。
- auto rollbackは現時点では行わない。
- /api/task/* /api/agent/* は追加しない。

## Known Current Code Facts

- PR-42 adds read-only code intelligence tools.
- PR-42B hardens Code Intel tools for large repositories.
- Code Intel supports single-file relative_path, safe per-file read failures, dependency resolution metadata, and safe related test verification hints.
- PR-42B does not add arbitrary command execution, remote git operations, auto rollback, or Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-43を実装する。
Nexus Context Refreshを追加し、implementation/debug/evaluation時に必要な追加情報をNexus経由で取得できるようにする。
ただし自動Web/DeepResearchの無制限実行は行わず、明示的なbudget/trigger/policyを設ける。

## Historical Compatibility Markers
- PR-ATLAS-PIPE-34
- PR-ATLAS-PIPE-35

## PR-ATLAS-PIPE-43 Context Refresh
- Adds bounded local-first Nexus Context Refresh bundles.
- Web/Deep Research require explicit manual policy and budget.
- No side effects: no safe_apply/verification/debug/patch/restore/rollback.
- Next: PR-ATLAS-PIPE-44 LLM Evaluator uses context bundle + diff/tests.


- PR-ATLAS-PIPE-43B hardens Context Refresh before LLM Evaluator: Nexus sources in bundle, changed_files metadata resolution, audit events, collector partial failure, and bundle API path-traversal safety.

Current PR: PR-ATLAS-PIPE-45B
Next PR: PR-ATLAS-PIPE-46 Bounded retry loop
\n## PR-ATLAS-PIPE-44B\n- Hardened evaluator: path safety, input packet resolution, diff_summary extraction, prompt contract, strict policy validation, no-side-effect guarantees.\n- Evaluator remains decision-only; PR-45 consumes evaluator results for multi-item guarded autopilot.


## PR-ATLAS-PIPE-44C
- Restores evaluator audit events and markdown persistence before multi-item autopilot.
- Evaluator results are saved as json and md.
- Evaluator emits evaluator_started/evaluator_completed/evaluator_fallback_used/evaluator_policy_override/evaluator_blocked/evaluator_failed.
- Evaluator remains decision-only and side-effect-free.
- Next: PR-ATLAS-PIPE-45 Multi-item guarded autopilot consumes evaluator results and audit events.

## Completed PRs
- PR-ATLAS-PIPE-0〜46: completed
- PR-SEARXNG-SECRET-SYNC-01: completed

## Current PR
- PR-ATLAS-PIPE-46B

## Next PR
- PR-ATLAS-PIPE-47: Supervised patch regeneration after failed verification with manual approval gate

- PR-ATLAS-PIPE-47B hardens supervised patch regeneration (audit events, prompt contract, evidence loading, target validation, manual approval only).

- PR-ATLAS-PIPE-48: Added manual approval gate for regenerated patch candidates; approved candidates now create safe_apply handoff artifacts only (no apply/verification/retry/rollback/restore/debug/autopilot resume). Next: PR-ATLAS-PIPE-49 supervised safe_apply execution from approved handoff.

- PR-ATLAS-PIPE-49: supervised safe_apply from approved handoff; requires approved handoff/hash/gate recheck; supports dry_run; safe_apply only; no verification/retry/rollback/restore. Next: PR-ATLAS-PIPE-50 supervised verification after handoff safe_apply.

- PR-ATLAS-PIPE-49B: Harden supervised handoff safe_apply atomicity, metadata updates, and audit events before verification.

Completed PRs:
- PR-ATLAS-PIPE-0〜49: completed
- PR-SEARXNG-SECRET-SYNC-01: completed

Current PR:
- PR-ATLAS-PIPE-49B

Next PR:
- PR-ATLAS-PIPE-50: Supervised verification after handoff safe_apply and result evaluation

- PR-ATLAS-PIPE-50: supervised handoff verification after applied safe_apply (allowlisted verification + local-only context refresh + evaluator, no rerun/retry/rollback/restore/debug/regen).

Next PR: PR-51 Optional bounded retry after failed supervised handoff verification

Current PR: PR-ATLAS-PIPE-50B

- PR-ATLAS-PIPE-51: Optional bounded retry after failed supervised handoff verification


- Completed PRs: PR-ATLAS-PIPE-0〜51, PR-ATLAS-UI-FIX-50A, PR-SEARXNG-SECRET-SYNC-01
- Current PR: PR-ATLAS-PIPE-51B
- Next PR: PR-ATLAS-PIPE-52: Close supervised loop by routing exhausted/not-retryable verification failures to patch regeneration recommendation

Current PR:
- PR-ATLAS-PIPE-52B

Next PR:
- PR-ATLAS-PIPE-53: Execute supervised patch regeneration from recommendation with manual trigger

## PR-ATLAS-PIPE-53 Checkpoint

Completed PRs:
- PR-ATLAS-PIPE-0〜52C: completed
- PR-ATLAS-UI-FIX-50A: completed
- PR-SEARXNG-SECRET-SYNC-01: completed

Current PR:
- PR-ATLAS-PIPE-53

Next PR:
- PR-ATLAS-PIPE-54: Finalize supervised item status transitions from loop outcomes

Known Current Code Facts:
- PR-53 manually executes supervised patch regeneration from saved recommendation payloads.
- PR-53 only creates patch candidates.
- PR-53 does not approve, apply, verify, retry, rollback, restore, run DebugReview, use remote git, or continue multi-item autopilot.
- Generated candidates remain manual approval required.

## PR-ATLAS-PIPE-54
- Finalizes PlanItem supervised status from loop artifacts.
- Calculates next_action but does not execute next_action.
- No safe_apply/verification/retry/patch regen/approval execution.
- Completes single-item supervised loop state tracking.
- Next PR: PR-ATLAS-PIPE-55 integrate supervised status into multi-item guarded autopilot.


## PR-ATLAS-PIPE-54B
- Hardened supervised item status finalization evidence selection with explicit source_type/source_run_id routing and created_at-prioritized latest selection.
- Added expanded audit events, detailed transition markdown, and best-effort persistence for item_not_found/exception paths.
- Enriched transition rules and next_action_payload contracts for approval/safe_apply/verification/retry/recommendation/manual investigation flows.

Current PR:
- PR-ATLAS-PIPE-54B

Next PR:
- PR-ATLAS-PIPE-55: Integrate supervised item status into multi-item guarded autopilot


Current PR:
- PR-ATLAS-PIPE-55

Next PR:
- PR-ATLAS-PIPE-56: Next Action Orchestrator for supervised multi-item workflow


## PR-ATLAS-PIPE-56
- Next Action Orchestrator added: reads multi-item supervised status queues, selects one next action, builds a normalized action contract, and saves JSON/Markdown artifacts.
- It does not execute next actions; manual confirmation remains required.
- No apply/verify/retry/approval/patch-regeneration/rollback/restore/debug-review/remote-git/autopilot-auto-continue actions are executed.
- Current PR: PR-ATLAS-PIPE-57B. Next PR: PR-ATLAS-PIPE-58: Refresh status queue after manual execution and recommend next manual step.
\n- PR-ATLAS-PIPE-58: Post Manual Execution Refresh reads manual executor result, refreshes supervised item status, rebuilds multi-item queue, prepares next manual action contract only (no execute/auto-continue).


## PR-ATLAS-PIPE-59B Operator Loop UI hardening
- Added UI-only operator loop over existing APIs: prepare -> dry_run -> execute one action -> refresh -> next step.
- Execute requires dry_run first and confirmation token/text (EXECUTE ONE ACTION).
- No auto continue, no execute all, no rollback/restore/debug/remote git, and no backend execution semantics added.
- Current PR: PR-ATLAS-PIPE-59B
- Next PR: PR-ATLAS-PIPE-60: Guarded semi-automatic operator loop with per-step confirmation
- PR-59B fixes Operator Loop state transition after refresh.
- Refresh prepares next action but does not execute it.
- Button guards and disabled reasons are now explicit.
- Confirmation token is never persisted.
- Execute remains dry-run-first and manual-click-only.


## PR-ATLAS-PIPE-59C update
- Hardened Manual Executor / Post Refresh CA_DATA root resolution via request-aware resolved root.
- Manual Executor persistence now writes final metadata before JSON/MD persistence.
- Root consistency is required before semi-auto; this PR adds no semi-auto or auto-continue behavior.


- PR-ATLAS-PIPE-60B hardens guarded semi-auto loop (UI binding, dry_run_next_action, policy flags, real tests).
- no full autonomous agent / no execute all / no auto continue / no follow-up execution after refresh.

Current PR:
- PR-ATLAS-PIPE-60C

Next PR:
- PR-ATLAS-SCALE-61: Persistent repo symbol index and incremental dependency graph

- PR-ATLAS-PIPE-60D completes CA_DATA root propagation for MultiStatus and NextActionOrchestrator.
- GuardedLoop / MultiStatus / Orchestrator / ManualExecutor / PostRefresh now use the same resolved root.
- Path("ca_data") direct usage is prohibited in these stacks.
- This PR does not add execute-all or auto-continue.
- PR-61 can now focus on persistent repo symbol index and dependency graph.


- PR-ATLAS-SCALE-61B completes Repo Index UI/API helpers.
- result endpoint returns saved artifact.
- files.json / manifest.json now contain file nodes/hash records.
- incremental update metadata added.
- Repo Intelligence UI remains manual-only.
- no PlanPool/patch/Guarded Loop integration yet.
- Current PR: PR-ATLAS-SCALE-61B
- Next PR: PR-ATLAS-SCALE-62: Use repo index in PlanPool scope analysis and context refresh

Current PR:
- PR-ATLAS-SCALE-62B

Next PR:
- PR-ATLAS-SCALE-63: Use repo context in planner prompt packaging and impacted-test recommendations

- PR-ATLAS-SCALE-63: Repo Context planner prompt packaging added (advisory/read-only).
- Impacted-test recommendations are suggestions only (no auto execution).
- No patch generation/safe_apply/verification/Guarded Loop integration.
- Repo Index missing remains non-blocking.


## PR-ATLAS-SCALE-63B
- fixes impacted-tests API root resolver.
- fixes PlanPool preflight packaging to use top-level changed_files/target_files (metadata fallback only when top-level empty).
- impacted-test recommendations remain suggestions only.
- no tests are executed.
- no patch/execution semantics changed.

Current PR:
- PR-ATLAS-SCALE-63B

Next PR:
- PR-ATLAS-SCALE-64: Use repo context for verification planning and CI/test selection hints without auto execution
