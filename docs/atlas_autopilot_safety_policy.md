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

## PR-ATLAS-PIPE-43 Context Refresh
- Adds bounded local-first Nexus Context Refresh bundles.
- Web/Deep Research require explicit manual policy and budget.
- No side effects: no safe_apply/verification/debug/patch/restore/rollback.
- Next: PR-ATLAS-PIPE-44 LLM Evaluator uses context bundle + diff/tests.


- PR-ATLAS-PIPE-43B hardens Context Refresh before LLM Evaluator: Nexus sources in bundle, changed_files metadata resolution, audit events, collector partial failure, and bundle API path-traversal safety.
