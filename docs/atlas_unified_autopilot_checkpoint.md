# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜22C: completed
- PR-ATLAS-PIPE-23: completed

## Current PR

- PR-ATLAS-PIPE-23B

## Next PR

- PR-ATLAS-PIPE-24: Manual patch proposal review / no auto apply

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

- PR-ATLAS-PIPE-23 adds manual DebugLoop review gate for failed verification items.
- Debug review is advisory only: root cause/proposed fix/reusable lesson.
- Debug review does not generate patches, does not run safe_apply, and does not rerun verification.
- Debug review is item-level/manual and never batch/full-autopilot.
- PR-ATLAS-PIPE-23B fixes the Debug Review API route and integration tests.
- PR-ATLAS-PIPE-23B does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-24を実装する。
DebugReviewのproposed_fixを元に、LLM/Plannerがpatch proposalを作る「提案レビュー」だけを追加する。ただしpatch自動適用・safe_apply自動実行・verification自動再実行はしない。
