# Atlas Autopilot Safety Policy (PR-ATLAS-PIPE-41B)

## Local Mode

- 認証なしで可能
- local repo inspection
- safe_apply
- snapshot
- restore
- verification
- dev tools

## GitHub Connected Mode

- 認証がある場合のみ
- clone/fetch/pull/push/PR/Actions 取得
- token をログに出さない
- token を docs/ca_data に保存しない
- GitHub auth is only needed for remote operations

## Forbidden

- no arbitrary command execution
- shell=True
- delete/run_command auto execution
- remote git operations from read-only tools
- auto rollback 現時点では禁止
- /api/task/* /api/agent/* 追加禁止

## Required

- project_path
- path validation
- snapshot before apply
- command allowlist
- bounded max files/bytes
- audit events
