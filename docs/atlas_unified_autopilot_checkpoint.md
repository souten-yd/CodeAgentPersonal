# Atlas Unified Autopilot Continuation Checkpoint

## Completed PRs

- PR-ATLAS-PIPE-0〜42: completed
- PR-SEARXNG-SECRET-SYNC-01: completed

## Current PR

- PR-ATLAS-PIPE-42B

## Next PR

- PR-ATLAS-PIPE-43: Nexus Context Refresh for implementation/debug/evaluation

## Important Constraints

- 任意コマンド実行は禁止。
- shell=Trueは禁止。
- auto rollbackは現時点では行わない。
- /api/task/* /api/agent/* は追加しない。

## Known Current Code Facts

- PR-42 adds read-only code intelligence tools.
- PR-42B hardens Code Intel tools for large repositories.
- Code Intel supports single-file relative_path, safe per-file read failures, dependency resolution metadata, and safe related test verification hints.
- PR-42B does not add arbitrary command execution, remote git operations, auto rollback, or Task/Agent APIs.

## Next Instruction

PR-ATLAS-PIPE-43を実装する。
Nexus Context Refreshを追加し、implementation/debug/evaluation時に必要な追加情報をNexus経由で取得できるようにする。
ただし自動Web/DeepResearchの無制限実行は行わず、明示的なbudget/trigger/policyを設ける。

## Historical Compatibility Markers
- PR-ATLAS-PIPE-34
- PR-ATLAS-PIPE-35
