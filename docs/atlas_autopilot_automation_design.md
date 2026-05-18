# Atlas Autopilot Automation Design (PR-ATLAS-PIPE-41B)

## Current Automation Loop

- Automation Gate
- one-item auto safe_apply
- Change Snapshot
- auto verification allowlist
- verification failure stop
- manual restore suggestion

## Current States

- planned
- auto_safe_apply_allowed
- auto_safe_apply_applied
- auto_verification_passed
- auto_verification_failed
- automation_stopped

## Future Loop

- multi-item guarded autopilot
- bounded retry
- Nexus Context Refresh
- LLM Evaluator
- supervised patch regeneration

## Failure Handling

- 現在は auto rollback しない
- manual restore suggestion のみ
- 将来 auto rollback は別 policy で導入

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
- Hardens bounded retry semantics so retryable transient failures continue until `max_attempts`.
- Reclassifies retryability on every verification rerun attempt.
- Enforces `max_runtime_seconds` and changed-file drift guard.
- Keeps safety invariants: no safe_apply rerun/rollback/restore/debug/patch regeneration.

- PR-ATLAS-PIPE-47B hardens supervised patch regeneration (audit events, prompt contract, evidence loading, target validation, manual approval only).

- PR-ATLAS-PIPE-48: Added manual approval gate for regenerated patch candidates; approved candidates now create safe_apply handoff artifacts only (no apply/verification/retry/rollback/restore/debug/autopilot resume). Next: PR-ATLAS-PIPE-49 supervised safe_apply execution from approved handoff.

- PR-ATLAS-PIPE-49: supervised safe_apply from approved handoff; requires approved handoff/hash/gate recheck; supports dry_run; safe_apply only; no verification/retry/rollback/restore. Next: PR-ATLAS-PIPE-50 supervised verification after handoff safe_apply.
