# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜36D: completed

## Current PR

- PR-ATLAS-PIPE-36E

## Next PR

- PR-ATLAS-PIPE-37: Manual Action Center for real-device implementation loop / no auto execution

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
- PR-36A adds concrete manual safe_apply executor proof for low-risk file updates.
- PR-36B adds manual restore from Change Snapshot without auto rollback.
- PR-36C unifies safe_apply executor, snapshot, and restore workspace root.
- API E2E proves safe_apply update changes a file and manual restore returns it to previous content.
- Restore remains manual only.
- Auto rollback is not enabled.
- PR-36D finalizes checkpoint/docs and strengthens create/restore E2E coverage.
- PR-36E wires Patch Proposal change content into PlanItem Draft safe_apply.
- Patch Proposal derived PlanItem Draft can carry executor-readable patch/proposed_content.
- Manual safe_apply from Patch Proposal draft can update a real file when executable change content exists.
- Manual restore can revert the change.
- Restore remains manual only.
- Auto rollback is not enabled.
- PR-36E does not add auto safe_apply, auto verification, auto DebugReview, auto Patch Proposal, auto rollback, or Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-37を実装する。Manual Action Centerを追加し、現在状態から次に押すべき手動アクションをトップ画面に表示する。ただし自動実行は行わない。
