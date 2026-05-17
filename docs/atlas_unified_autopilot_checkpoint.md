# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜30: completed

## Current PR

- PR-ATLAS-PIPE-30B

## Next PR

- PR-ATLAS-PIPE-31: Manual Patch Proposal approval UX/E2E from generated proposal / no draft auto-create

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
- PR-ATLAS-PIPE-27 verifies approved draft PlanItems can be manually safe_applied through the existing safe_apply gate.
- PR-ATLAS-PIPE-28 improves manual post-apply verification UX for draft safe_apply results.
- Draft safe_apply results appear as manual verification candidates.
- Verification remains item-level/manual only.
- Failed verification does not auto-start DebugLoop.
- PR-ATLAS-PIPE-29 improves manual Debug Review UX/E2E for failed draft verification.
- Debug Review remains item-level/manual only.
- Debug Review does not auto-generate Patch Proposal, does not run safe_apply, and does not rerun verification.
- PR-ATLAS-PIPE-29B finalizes Debug Review checkpoint/docs and strengthens no-auto-patch assertions.
- PR-ATLAS-PIPE-30 improves manual Patch Proposal UX/E2E from DebugReview analyzed result.
- DebugReview analyzed draft items appear as manual Patch Proposal candidates.
- Patch Proposal generation remains item-level/manual only.
- Patch Proposal generation does not auto-approve, does not create PlanItem draft, does not run safe_apply, and does not rerun verification.
- Patch Proposal may use llm_json_fn when available; otherwise fallback proposal is generated.
- PR-ATLAS-PIPE-30B finalizes checkpoint/docs and fixes continuation next_action after patch proposal generation.
- PR-ATLAS-PIPE-30B does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-31を実装する。
manual Patch Proposal generated結果から、Patch Proposal Approval panelへ自然に誘導し、手動approve/reject/needs_revision UX/E2Eを整える。ただしPlanItem draft自動作成・patch自動適用・safe_apply自動実行・verification自動再実行は行わない。
