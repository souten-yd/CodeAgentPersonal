# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜39B: completed

## Current PR

- PR-ATLAS-PIPE-39C

## Next PR

- PR-ATLAS-PIPE-40: Verification failure stop policy and manual restore suggestion / no auto rollback

## Important Constraints

- 自動safe_applyはしない。
- 自動verificationはしない。
- 自動DebugReviewはしない。
- 自動Patch Proposalはしない。
- 自動rollbackはしない。
- restoreは手動のみ。
- delete/run_commandは禁止維持。
- shell=Trueは禁止。
- /api/task/* /api/agent/* は追加しない。

## Known Current Code Facts

- PR-ATLAS-PIPE-34 adds final real-device smoke/checklist and reload recovery checks.
- PR-ATLAS-PIPE-35 adds Change Snapshot backup before manual safe_apply.
- PR-ATLAS-PIPE-36A adds concrete manual safe_apply executor proof for low-risk file updates.
- PR-ATLAS-PIPE-36B adds manual restore from Change Snapshot without auto rollback.
- PR-ATLAS-PIPE-36C unifies safe_apply executor, snapshot, and restore workspace root.
- PR-ATLAS-PIPE-36D finalizes checkpoint/docs and strengthens create/restore E2E coverage.
- PR-ATLAS-PIPE-36E wires Patch Proposal change content into PlanItem Draft safe_apply.
- PR-ATLAS-PIPE-36F hardens Patch Proposal draft safe_apply E2E assertions.
- PR-ATLAS-PIPE-36G fixes project_path persistence/storage sync for Patch Proposal draft safe_apply E2E.
- PR-ATLAS-PIPE-37 adds Auto Policy Presets and Automation Gate.
- PR-ATLAS-PIPE-38 adds gated auto safe_apply for exactly one guarded_low_risk approved item.
- PR-39 adds allowlisted auto verification after gated auto safe_apply.
- PR-39B requires project_path before auto verification and adds initial auto verification E2E coverage.
- PR-39C strictly asserts auto verification pass/fail E2E.
- safe-apply-one-and-verify success requires applied_and_verified.
- verification failure requires applied_but_verification_failed and does not auto restore/debug/patch/rollback.
- Arbitrary command input remains forbidden.
- shell=True remains forbidden.
- PR-39C does not add batch execution, auto rollback, auto DebugReview, auto Patch Proposal, or Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-40を実装する。
auto verification失敗時に停止し、Change Snapshotからmanual restore候補を提示する。ただしauto rollbackはまだ行わない。
