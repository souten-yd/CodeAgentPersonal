# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜28: completed

## Current PR

- PR-ATLAS-PIPE-29

## Next PR

- PR-ATLAS-PIPE-30: Manual Patch Proposal UX/E2E from DebugReview result / no auto apply

## Important Constraints

- Verificationはitem-level/manualのみ。
- Debug reviewはitem-level/manualのみ。
- batch/full-autopilot verification/debug reviewは禁止。
- arbitrary command inputは禁止。
- Debug reviewはadvisory only。
- patch自動生成・safe_apply自動実行・verification自動再実行は禁止。
- DeepResearch/Web jobは起動しない。
- /api/task/* /api/agent/* は追加しない。

## Known Current Code Facts

- PR-ATLAS-PIPE-25B locks approved/rejected patch proposals to avoid approval/proposal metadata mismatch.
- PR-ATLAS-PIPE-26 converts approved Patch Proposal into approval_required PlanItem draft.
- Conversion does not apply patches, does not run safe_apply, and does not run verification.
- Draft PlanItem still requires normal PlanItem approval before manual safe_apply.
- PR-ATLAS-PIPE-26B/26C verifies draft PlanItem appears in Approval Gate and can become a safe_apply candidate after approval.
- PR-ATLAS-PIPE-26C fixes Dashboard approval refresh after draft creation.
- PR-ATLAS-PIPE-29 verifies approved draft PlanItems can be manually safe_applied through the existing safe_apply gate.
- PR-ATLAS-PIPE-28 improves manual post-apply verification UX for draft safe_apply results.
- Draft safe_apply results appear as manual verification candidates.
- Verification remains item-level/manual only.
- Draft safe_apply requires normal PlanItem approval.
- Draft safe_apply does not auto-run verification, DebugLoop, or Patch Proposal regeneration.
- Executor-unavailable still blocks normal safe_apply.
- PR-ATLAS-PIPE-29 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-29を実装する。
draft由来PlanItemのmanual verification failed結果から、Debug Review panelへ自然に誘導し、手動DebugReview UX/E2Eを整える。ただし自動patch生成・自動safe_apply・自動再verificationは行わない。

- Failed verification does not auto-start DebugLoop.
- PR-ATLAS-PIPE-29 improves manual Debug Review UX/E2E for failed draft verification.
- Debug Review remains item-level/manual only.
- Debug Review does not auto-generate Patch Proposal, does not run safe_apply, and does not rerun verification.
- PR-ATLAS-PIPE-29 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.
