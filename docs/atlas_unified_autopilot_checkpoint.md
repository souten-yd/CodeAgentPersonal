# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜37: completed

## Current PR

- PR-ATLAS-PIPE-38

## Next PR

- PR-ATLAS-PIPE-39: Auto verification after gated auto safe_apply / no auto rollback

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
- PR-36F hardens Patch Proposal draft safe_apply E2E assertions.
- PR-36F hardened Patch Proposal draft safe_apply E2E assertions and exposed failing behavior.
- PR-36G fixes project_path persistence / storage sync for Patch Proposal draft safe_apply E2E.
- Patch Proposal draft safe_apply E2E now proves repo file changes old → new.
- Manual restore E2E now proves repo file returns new → old.
- content_missing cannot pass as applied.
- PR-36G does not add auto safe_apply, auto verification, auto DebugReview, auto Patch Proposal, auto rollback, or Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-39を実装する。gated auto safe_apply成功後に、allowlistされたverification commandだけを自動実行する。ただしverification失敗時のauto restore/rollback、DebugReview、Patch Proposalはまだ行わない。


Next PR:
- PR-ATLAS-PIPE-39: Auto verification after gated auto safe_apply / no auto rollback

- PR-36G proves Patch Proposal draft safe_apply changes repo file old → new and manual restore returns new → old.
- PR-37 adds Auto Policy Presets and Automation Gate.
- PR-37 only decides automation readiness and does not execute safe_apply automatically.
- guarded_low_risk preset can allow auto safe_apply only for approved low-risk create/update items with safe target_files, project_path, snapshot requirement, and executor-readable patch content.
- PR-37 does not add auto verification, auto DebugReview, auto Patch Proposal, auto rollback, or Task/Agent APIs.
- PR-38 adds gated auto safe_apply for exactly one guarded_low_risk approved item.
- Auto safe_apply requires project_path, approval, safe target_files, executor-readable patch content, and Change Snapshot.
- Snapshot is created before auto safe_apply executor is called.
- PR-38 does not add auto verification, auto DebugReview, auto Patch Proposal, auto rollback, batch execution, or Task/Agent APIs.


- PR-38 adds gated auto safe_apply for exactly one guarded_low_risk approved item.
- PR-39 adds allowlisted auto verification after gated auto safe_apply.
- Verification commands are allowlisted only.
- Arbitrary command input is forbidden.
- Auto verification failure stops the loop and does not auto restore, debug, or patch.
- PR-39 does not add auto rollback, auto DebugReview, auto Patch Proposal, batch execution, or Task/Agent APIs.


## Current PR
- PR-ATLAS-PIPE-39B

## Next PR
- PR-ATLAS-PIPE-40: Verification failure stop policy and manual restore suggestion / no auto rollback

## Known Current Code Facts (PR-39B)
- PR-39 adds allowlisted auto verification after gated auto safe_apply.
- PR-39B hardens auto verification pass/fail E2E coverage.
- Auto verification requires project_path and does not run from server current directory.
- safe-apply-one-and-verify proves auto safe_apply followed by allowlisted verification.
- Verification failure stops the loop and does not auto restore, debug, patch, or rollback.
- Arbitrary command input remains forbidden.
- shell=True remains forbidden.
- PR-39B does not add batch execution, auto rollback, auto DebugReview, auto Patch Proposal, or Task/Agent APIs.
