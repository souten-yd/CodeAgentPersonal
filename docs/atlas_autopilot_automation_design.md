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

