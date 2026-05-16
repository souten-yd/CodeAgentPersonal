# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜23B: completed

## Current PR

- PR-ATLAS-PIPE-24

## Next PR

- PR-ATLAS-PIPE-25: Patch proposal approval gate / no apply

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
- PR-ATLAS-PIPE-24 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-25を実装する。
Patch Proposalをユーザーがapprove/reject/needs_revisionできるapproval gateを追加する。ただしpatch適用・safe_apply実行・verification再実行はまだ行わない。
