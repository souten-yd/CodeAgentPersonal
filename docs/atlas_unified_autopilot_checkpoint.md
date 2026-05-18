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
