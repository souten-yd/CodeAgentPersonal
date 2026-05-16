# Atlas Unified Autopilot Continuation Checkpoint

## Current Goal

Atlasを Planner + Autopilot + Plan Pool + Nexus Research Pipeline へ統合する。

## Completed PRs

- PR-ATLAS-PIPE-0: completed
- PR-ATLAS-PIPE-1: completed
- PR-ATLAS-PIPE-2: completed
- PR-ATLAS-PIPE-3: completed
- PR-ATLAS-PIPE-4: completed
- PR-ATLAS-PIPE-5: completed
- PR-ATLAS-PIPE-6: completed
- PR-ATLAS-PIPE-7: completed
- PR-ATLAS-PIPE-8: completed
- PR-ATLAS-PIPE-8B: completed
- PR-ATLAS-PIPE-9: completed
- PR-ATLAS-PIPE-10: completed
- PR-ATLAS-PIPE-11: completed
- PR-ATLAS-PIPE-12: completed
- PR-ATLAS-PIPE-13: completed
- PR-ATLAS-PIPE-14: completed
- PR-ATLAS-PIPE-14B: completed
- PR-ATLAS-PIPE-14C: completed
- PR-ATLAS-PIPE-15: completed
- PR-ATLAS-PIPE-15B: completed
- PR-ATLAS-PIPE-16: completed
- PR-ATLAS-PIPE-17: completed
- PR-ATLAS-PIPE-18: completed
- PR-ATLAS-PIPE-18B: completed
- PR-ATLAS-PIPE-19: completed
- PR-ATLAS-PIPE-20: completed
- PR-ATLAS-PIPE-20B: completed
- PR-ATLAS-PIPE-21: completed
- PR-ATLAS-PIPE-21B: completed
- PR-ATLAS-PIPE-21C: completed

## Current PR

PR-ATLAS-PIPE-22

## Next PR

PR-ATLAS-PIPE-23: Manual DebugLoop review gate / no auto patch

## Important Constraints

- safe_applyは承認済み・low risk・1 item・手動のみ。
- batch/full-autopilot applyは禁止。
- delete/run_commandは引き続き禁止。
- TestCommandRunner / DebugLoopRunner / DeepResearchの自動実行は禁止。

## Known Current Code Facts

- PR-ATLAS-PIPE-21C aligns manual safe_apply approval semantics and makes previous tests pass.
- PR-ATLAS-PIPE-22 removes noop executor applied semantics.
- executor unavailable blocks normal safe_apply unless dry_run simulation is explicitly requested.
- safe_apply remains item-level only and never batch/full-autopilot.
- delete/run_command and medium/high/critical risk items remain blocked.
- TestCommandRunner/DebugLoopRunner/DeepResearch are not auto-run.

## Next Instruction

PR-ATLAS-PIPE-23を実装する。
verification failed itemに対して、DebugLoopRunnerの分析/提案だけを手動で実行できるreview gateを追加する。ただし自動patch生成・自動safe_apply・自動再検証は行わない。


- PR-ATLAS-PIPE-22 adds manual post-apply verification gate for safe_applied PlanItems.
- Verification uses allowlisted TestCommandRunner only.
- Verification is item-level/manual and never batch/full-autopilot.
- Failed verification does not start DebugLoop or auto-fix.
- PR-ATLAS-PIPE-22 does not execute DeepResearch/Web jobs and does not add Task/Agent APIs.

Next PR
- PR-ATLAS-PIPE-23: Manual DebugLoop review gate / no auto patch
