# Atlas Play / Capsule / Portal Current Status

> Mutable checkpoint for Codex or Claude goal mode.
> Update this file after every work package.

## Goal status

- Overall: In progress
- Baseline: `8d6897fe366a3877808f040a8828729350b89b7e`
- Canonical goal: `docs/atlas_play_portal_capsule_goal.md`
- Atlas Play specification: `docs/atlas_play_spec.md`
- Capsule and Portal specification: `docs/atlas_capsule_portal_spec.md`
- Canonical plan: `docs/atlas_play_portal_capsule_implementation_plan.md`
- Current work package: PR-PPC-2
- Next action: implement Play target and dependency discovery

## Baseline observations

- Atlas already has an isolated project working directory under `ca_data/atlas/projects/<name>/work`.
- Atlas project APIs already list, create, delete, persist conversation and download a development archive.
- The Atlas conversational shell is the visible Atlas UI; the legacy dashboard remains hidden for compatibility.
- The project picker and Plan History button are injected from `web/js/app.js` into `.atlas-claude-header-actions`.
- Atlas intent classification is implemented in `web/js/atlas_claude_panel.js` and currently recognizes `/plan`, not `/play`.
- New routers are added under `app/api/*` and registered through `app/server.py:include_routers()`. Lifespan, middleware and direct routes still live in `main.py`, and the production app remains `main:app`.
- Startup orphan reconciliation for Play/Portal processes, ports, staging roots and incomplete commits must be registered in `main.py` lifespan when those runtime packages are implemented.
- `app/atlas/` currently has no subprocess/Popen/os.system/create_subprocess runtime path. Play/Portal introduces a new user-selected artifact runtime boundary, not Atlas agent autonomous command execution.
- Safe Apply already validates relative targets under a workspace root; Play requires a broader shared read/write/execute/serve policy without weakening Safe Apply.
- No Portal top-level mode, Play session runtime, Capsule package contract or Portal data lifecycle exists yet.

## Work package table

| Package | Title | Status | Evidence |
|---|---|---|---|
| PR-PPC-0 | Baseline, contracts and threat model | Completed | `python -m pytest -q tests/test_atlas_play_portal_capsule_ppc0_contracts.py` -> 8 passed; affected router/API slice -> 16 passed; `python -m py_compile ...` -> passed |
| PR-PPC-1 | Workspace access policy and file service | Completed | `python -m pytest -q tests/test_atlas_play_workspace_policy.py` -> 11 passed, 1 skipped; affected policy/snapshot/Safe Apply slice -> 48 passed, 5 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-2 | Play target and dependency discovery | Not started | - |
| PR-PPC-3 | Environment resolver and launch adapters | Not started | - |
| PR-PPC-4 | Process supervisor and Play sessions | Not started | - |
| PR-PPC-4b | Composite runtime startup and cleanup | Not started | - |
| PR-PPC-5a | Session-bound static preview serving | Not started | - |
| PR-PPC-5b | Reverse proxy, WebSocket and SSE gateway | Not started | - |
| PR-PPC-6 | Atlas Play mobile workspace and controls | Not started | - |
| PR-PPC-7 | Capsule analysis and builder | Not started | - |
| PR-PPC-8 | Portal catalog, import and export | Not started | - |
| PR-PPC-9 | Portal staging and shared runtime launch | Not started | - |
| PR-PPC-10 | Persistent data, discard and snapshots | Not started | - |
| PR-PPC-11 | Disconnect recovery and lifecycle hardening | Not started | - |
| PR-PPC-12 | Acceptance, security and mobile E2E | Not started | - |

## Safety checkpoint

PR-PPC-1 adds shared workspace access decisions and bounded Play file list/read/write APIs under the selected Atlas project work root. It does not add process execution, preview serving, package extraction, Portal data writes, general shell access or UI authority. Existing Atlas workflow state, PlanPool, approval, critical-event, allowed-path, rollback and retry boundaries are unchanged.

## Latest completed package evidence

Completed package:
PR-PPC-1 - Workspace access policy and file service.

PR/commit:
PR #1617 package commit.

Changed files:
- `app/api/atlas_play.py`
- `app/atlas/play/workspace_policy.py`
- `app/atlas/play/file_service.py`
- `tests/test_atlas_play_workspace_policy.py`
- `docs/atlas_play_portal_capsule_current_status.md`

Public contracts added or changed:
- Added versioned workspace access policy decisions with independent `read`, `write`, `execute` and `serve` permissions.
- Added bounded Play workspace file list/read/write service.
- Added `/api/atlas/play/workspace/files/list`, `/read` and `/write` endpoints scoped to `ca_data/atlas/projects/<project>/work`.

Behavior implemented:
- Path normalization rejects traversal, encoded traversal, absolute paths, Windows drives, UNC paths and empty path segments.
- Existing symlinks/junction-like escapes are rejected before read/write/list operations.
- Protected dependency/runtime directories such as `.git`, `.venv`, `node_modules`, `dist`, `build` and `ca_data` are excluded from normal file APIs.
- File reads are bounded by size, text encoding and binary-file checks.
- Writes require an optimistic SHA-256 precondition or the `absent` marker for new files.
- Stale writes return conflict without modifying the target file.

Focused tests:
- `python -m pytest -q tests/test_atlas_play_workspace_policy.py` -> 11 passed, 1 skipped.

Syntax checks:
- `python -m py_compile app\atlas\play\workspace_policy.py app\atlas\play\file_service.py app\api\atlas_play.py` -> passed.

Affected tests:
- `python -m pytest -q tests/test_atlas_play_workspace_policy.py tests/test_atlas_file_safe_apply_executor.py tests/test_atlas_workspace_snapshot_service.py tests/test_atlas_play_portal_capsule_ppc0_contracts.py` -> 48 passed, 5 skipped.

Safety invariants verified:
- Safe Apply code paths were not weakened or modified.
- Play file writes remain project-root scoped and require revision preconditions.
- No process execution, preview gateway, package extraction, Portal data write, general shell endpoint or raw host-filesystem serving was added.

Known limitations:
- Symlink tests are skipped when the platform does not allow symlink creation in the test environment.
- PR-PPC-1 does not implement Play target discovery, launch adapters, preview or runtime sessions.

Remaining gaps:
- PR-PPC-2 Play target and dependency discovery.

Next package:
PR-PPC-2 - Play target and dependency discovery.

## Update template

After each package record:

```text
Completed package:
PR/commit:
Changed files:
Public contracts added or changed:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Safety invariants verified:
Known limitations:
Remaining gaps:
Next package:
```
