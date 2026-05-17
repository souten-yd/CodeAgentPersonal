# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜33: completed

## Current PR

- PR-ATLAS-PIPE-34

## Next PR

- PR-ATLAS-PIPE-35: Change Snapshot backup before safe_apply / no auto rollback

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

- PR-ATLAS-PIPE-31 improves manual Patch Proposal approval UX/E2E from generated proposal.
- PR-ATLAS-PIPE-32 improves manual PlanItem draft creation UX/E2E from approved Patch Proposal.
- PR-ATLAS-PIPE-33 improves manual PlanItem approval UX/E2E for generated draft.
- Manual loop is connected through: Patch Proposal generate → Patch Proposal approve → PlanItem draft create → PlanItem approve → manual safe_apply candidate.
- PlanItem approval remains item-level/manual only.
- PlanItem approval does not run safe_apply, verification, DebugReview, or Patch Proposal generation.
- PR-ATLAS-PIPE-34 adds final real-device smoke/checklist and reload recovery checks.
- PR-ATLAS-PIPE-34 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-35を実装する。safe_apply前に対象ファイルのChange Snapshot backupを保存する仕組みを追加する。ただしこのPRでは自動rollbackは行わない。

- Current PR: PR-ATLAS-PIPE-35
- Next PR: PR-ATLAS-PIPE-36: Manual restore from Change Snapshot / no auto rollback
- Known Current Code Facts:
  - PR-ATLAS-PIPE-35 adds Change Snapshot backup before manual safe_apply.
  - Change Snapshot is saved before safe_apply executor is called.
  - Snapshot failure blocks safe_apply.
  - PR-ATLAS-PIPE-35 does not perform restore/rollback automatically.
  - PR-ATLAS-PIPE-35 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.
