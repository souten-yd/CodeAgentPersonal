# Atlas Unified Autopilot Continuation Checkpoint

## Completed PRs

- PR-ATLAS-PIPE-0〜41: completed
- PR-SEARXNG-SECRET-SYNC-01: completed

## Current PR

- PR-ATLAS-PIPE-41B

## Next PR

- PR-ATLAS-PIPE-42: Dev Tooling Pack 2 - symbol index, dependency graph, related tests


## Important Constraints

- 任意コマンド実行は禁止。
- shell=Trueは禁止。
- auto rollbackは現時点では行わない。
- /api/task/* /api/agent/* は追加しない。

## Known Current Code Facts

- PR-ATLAS-PIPE-34 adds final real-device smoke/checklist and reload recovery checks.
- PR-ATLAS-PIPE-35 adds Change Snapshot backup before manual safe_apply.
- PR-40 adds verification failure stop policy and manual restore suggestion.
- PR-41 adds scalable read-only local repo inspection tools.
- PR-SEARXNG-SECRET-SYNC-01 fixes Windows SearXNG settings.yml server.secret_key sync.
- PR-41B creates scale autopilot design docs and reconciles checkpoint.
- Local repo mode works without GitHub authentication.
- GitHub authentication is optional and needed only for remote operations.

## Next Instruction

PR-ATLAS-PIPE-42を実装する。
Dev Tooling Pack 2として、symbol index、dependency graph、related tests finderを追加する。
ただし任意コマンド実行、remote git操作、auto rollback、Task/Agent APIは追加しない。
