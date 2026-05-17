# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜32: completed

## Current PR

- PR-ATLAS-PIPE-33

## Next PR

- PR-ATLAS-PIPE-34: Manual loop final real-device smoke checklist / no auto execution

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

- PR-ATLAS-PIPE-33 improves manual Patch Proposal approval UX/E2E from generated proposal.
- Generated Patch Proposal can be approved/rejected/needs_revision manually.
- Patch Proposal approval remains item-level/manual only.
- Patch Proposal approval does not auto-create PlanItem draft, does not apply patch, does not run safe_apply, and does not rerun verification.
- PR-ATLAS-PIPE-33 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-34を実装する。実機テスト前の最終manual loop smoke/checklistを整備する。UI/APIで、Patch Proposal生成からmanual safe_apply候補表示までの一連の手動操作を確認できるようにし、リロード後の状態復元も確認する。ただし自動safe_apply・自動verification・自動DebugReviewは行わない。


- PR-ATLAS-PIPE-33 improves manual PlanItem draft creation UX/E2E from approved Patch Proposal.
- PlanItem draft creation remains item-level/manual only.
- PlanItem draft creation does not auto-approve PlanItem, does not run safe_apply, and does not rerun verification.
- PR-ATLAS-PIPE-33 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

- PR-ATLAS-PIPE-31 improves manual Patch Proposal approval UX/E2E from generated proposal.
- PR-ATLAS-PIPE-32 improves manual PlanItem draft creation UX/E2E from approved Patch Proposal.
- PR-ATLAS-PIPE-33 improves manual PlanItem approval UX/E2E for generated draft.
- Manual loop is now connected through: Patch Proposal generate → Patch Proposal approve → PlanItem draft create → PlanItem approve → manual safe_apply candidate.
- PlanItem approval remains item-level/manual only.
- PlanItem approval does not run safe_apply, verification, DebugReview, or Patch Proposal generation.
- PR-ATLAS-PIPE-33 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.
