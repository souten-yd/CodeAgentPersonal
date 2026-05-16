# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0〜21D: completed
- PR-ATLAS-PIPE-22: completed

## Current PR

- PR-ATLAS-PIPE-22B

## Next PR

- PR-ATLAS-PIPE-23: Manual DebugLoop review gate / no auto patch

## Important Constraints

- Verificationはitem-level/manualのみ。
- batch/full-autopilot verificationは禁止。
- arbitrary command inputは禁止。
- TestCommandRunnerはallowlisted commandのみ。
- failed verificationでもDebugLoop/auto-fixは起動しない。
- DeepResearch/Web jobは起動しない。
- /api/task/* /api/agent/* は追加しない。

## Known Current Code Facts

- PR-ATLAS-PIPE-21D removes noop executor applied semantics.
- executor unavailable blocks normal safe_apply unless dry_run simulation is explicitly requested.
- PR-ATLAS-PIPE-22 adds manual post-apply verification gate for safe_applied PlanItems.
- Verification uses allowlisted TestCommandRunner only.
- Verification is item-level/manual and never batch/full-autopilot.
- Failed verification does not start DebugLoop or auto-fix.
- PR-ATLAS-PIPE-22B fixes the verification API endpoint and test isolation.
- PR-ATLAS-PIPE-22B does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-23を実装する。
verification failed itemに対して、DebugLoopRunnerの分析/提案だけを手動で実行できるreview gateを追加する。ただし自動patch生成・自動safe_apply・自動再検証は行わない。
