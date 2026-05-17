# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜26B: completed

## Current PR

- PR-ATLAS-PIPE-26C

## Next PR

- PR-ATLAS-PIPE-27: Manual safe_apply execution for approved draft PlanItem / no auto verification

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
- PR-ATLAS-PIPE-26C does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-27を実装する。
approved draft PlanItemを、既存manual safe_apply gateで安全に実行できることをUI/API/E2E的に整える。ただし自動verification・自動debug loop・自動再提案はまだ行わない。
