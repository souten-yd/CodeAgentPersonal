# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜30B: completed

## Current PR

- PR-ATLAS-PIPE-31

## Next PR

- PR-ATLAS-PIPE-32: Manual PlanItem draft creation UX/E2E from approved Patch Proposal / no auto safe_apply

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
- Generated Patch Proposal can be approved/rejected/needs_revision manually.
- Patch Proposal approval remains item-level/manual only.
- Patch Proposal approval does not auto-create PlanItem draft, does not apply patch, does not run safe_apply, and does not rerun verification.
- PR-ATLAS-PIPE-31 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-32を実装する。manual approved Patch Proposal結果から、PlanItem Draft作成panelへ自然に誘導し、手動PlanItem draft作成UX/E2Eを整える。ただしPlanItem approval自動実行・safe_apply自動実行・verification自動再実行は行わない。
