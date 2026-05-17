# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜26: completed

## Current PR

- PR-ATLAS-PIPE-26B

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

- PR-ATLAS-PIPE-24 adds manual patch proposal review from DebugReview results.
- Patch proposal is advisory only and saved as JSON/MD.
- Patch proposal does not apply patches, does not run safe_apply, and does not rerun verification.
- Patch proposal may use llm_json_fn when available, otherwise fallback proposal is generated.
- PR-ATLAS-PIPE-26B hardens LLM patch proposal normalization so untrusted fields cannot mark proposals as applied/accepted.
- PR-ATLAS-PIPE-26B normalizes risk_level, filters unsafe target_files, and truncates large diff previews.
- PR-ATLAS-PIPE-26B does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-26を実装する。
approved Patch Proposalを、手動safe_apply可能なPlanItem draftへ変換する。ただし自動safe_apply・自動verification・自動debug loopは実行しない。

- PR-ATLAS-PIPE-25 adds patch proposal approval gate.
- Patch Proposal can be approved/rejected/needs_revision by the user.
- Approval records are saved as JSON/MD and reflected in PlanItem metadata.
- Patch proposal approval does not apply patches, does not run safe_apply, and does not rerun verification.
- PR-ATLAS-PIPE-25 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.
- PR-ATLAS-PIPE-26B locks approved/rejected patch proposals to avoid approval/proposal metadata mismatch.
- PR-ATLAS-PIPE-26B keeps patch/safe_apply/verification execution disabled.

- PR-ATLAS-PIPE-26 converts approved Patch Proposal into approval_required PlanItem draft.
- Conversion does not apply patches, does not run safe_apply, and does not run verification.
- Draft PlanItem still requires normal PlanItem approval before manual safe_apply.
- PR-ATLAS-PIPE-26 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.
- PR-ATLAS-PIPE-26B verifies draft PlanItem appears in Approval Gate and can become a safe_apply candidate after approval.
- PR-ATLAS-PIPE-26B does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-27を実装する。
approved draft PlanItemを、既存manual safe_apply gateで安全に実行できることをUI/API/E2E的に整える。ただし自動verification・自動debug loop・自動再提案はまだ行わない。
