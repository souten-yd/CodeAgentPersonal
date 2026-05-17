# Atlas Dev Tooling Design (PR-ATLAS-PIPE-41B)

## Scope

- 既存 legacy tools は参考のみ
- PR-41 で新規 read-only local repo inspection tools が追加済み

## Implemented in PR-41

- git_status
- git_diff
- git_ls_files
- project_tree
- list_files
- file_outline

## Path Safety

- project_path 必須
- absolute path 禁止
- `..` 禁止
- home expansion 禁止
- symlink escape 禁止

## Git Policy

- 許可: status/diff/ls-files のみ
- 禁止: clone/fetch/pull/push/checkout/reset/clean/commit/config/submodule update

## Large Repo Behavior

- max_files
- max_bytes
- max_depth
- binary skip
- large file skip

## Planned for PR-42

- symbol_index
- dependency_graph
- related_tests
