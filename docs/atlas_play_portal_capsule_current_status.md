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
- Current work package: PR-PPC-10
- Next action: implement Portal persistent data, discard and snapshots

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
| PR-PPC-2 | Play target and dependency discovery | Completed | `python -m pytest -q tests/test_atlas_play_target_discovery.py` -> 6 passed; affected Play/Lumen slice -> 29 passed, 1 skipped; `python -m py_compile ...` and `node --check ...` -> passed |
| PR-PPC-3 | Environment resolver and launch adapters | Completed | `python -m pytest -q tests/test_atlas_play_environment_adapters.py` -> 7 passed; affected Play contract slice -> 32 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-4 | Process supervisor and Play sessions | Completed | `python -m pytest -q tests/test_atlas_play_process_sessions.py` -> 10 passed; affected Play contract slice -> 42 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-4b | Composite runtime startup and cleanup | Completed | `python -m pytest -q tests/test_atlas_play_composite_runtime.py` -> 5 passed; affected Play runtime slice -> 47 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-5a | Session-bound static preview serving | Completed | `python -m pytest -q tests/test_atlas_play_static_preview.py` -> 5 passed; affected Play runtime slice -> 52 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-5b | Reverse proxy, WebSocket and SSE gateway | Completed | `python -m pytest -q tests/test_atlas_play_proxy_gateway.py` -> 6 passed; affected Play runtime slice -> 58 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-6 | Atlas Play mobile workspace and controls | Completed | `python -m pytest -q tests/test_atlas_play_mobile_workspace_ui_contract.py` -> 5 passed; affected Play/UI slice -> 63 passed, 1 skipped; `node --check ...` -> passed |
| PR-PPC-7 | Capsule analysis and builder | Completed | `python -m pytest -q tests/test_atlas_capsule_builder.py` -> 6 passed; affected Play/Capsule slice -> 69 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-8 | Portal catalog, import and export | Completed | `python -m pytest -q tests/test_portal_catalog.py` -> 6 passed; affected Portal/Capsule/Play slice -> 75 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-9 | Portal staging and shared runtime launch | Completed | `python -m pytest -q tests/test_portal_runtime.py` -> 6 passed; affected Portal/Capsule/Play slice -> 81 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-10 | Persistent data, discard and snapshots | Not started | - |
| PR-PPC-11 | Disconnect recovery and lifecycle hardening | Not started | - |
| PR-PPC-12 | Acceptance, security and mobile E2E | Not started | - |

## Safety checkpoint

PR-PPC-9 adds Portal installation, safe application staging and runtime launch through the shared Play session manager. It does not directly spawn processes from Portal code, install dependencies, mutate package archives, implement persistent data commits or change workflow_state / PlanPool authority. Existing Atlas workflow state, approval, critical-event, allowed-path, rollback and retry boundaries are unchanged.

## Latest completed package evidence

Completed package:
PR-PPC-9 - Portal staging and shared runtime launch.

PR/commit:
PR-PPC-9 package branch.

Changed files:
- `app/api/portal.py`
- `app/portal/runtime.py`
- `tests/test_portal_runtime.py`
- `tests/test_atlas_play_portal_capsule_ppc0_contracts.py`
- `docs/atlas_play_portal_capsule_current_status.md`

Public contracts added or changed:
- Portal capabilities now enable run.
- Added Portal install, run, stop and purge endpoints.
- Portal runtime records map installation id, portal session id, play session id, application root and launch profile.

Behavior implemented:
- Every run revalidates stored package content hash before extraction.
- Application files are safely extracted into Portal session application root.
- Extracted application files are marked read-only.
- Launch profile selection supports single-process and composite profiles.
- Portal run requests are mapped to PlaySessionManager start/start_composite calls.
- Untrusted imported packages remain blocked without explicit override acknowledgement.
- Stop and purge use Play session manager and remove disposable staged application, cache and temp content.

Focused tests:
- `python -m pytest -q tests/test_portal_runtime.py` -> 6 passed.

Syntax checks:
- `python -m py_compile app\portal\runtime.py app\api\portal.py tests\test_portal_runtime.py tests\test_atlas_play_portal_capsule_ppc0_contracts.py` -> passed.

Affected tests:
- `python -m pytest -q tests/test_portal_runtime.py tests/test_portal_catalog.py tests/test_atlas_capsule_builder.py tests/test_atlas_play_mobile_workspace_ui_contract.py tests/test_atlas_play_proxy_gateway.py tests/test_atlas_play_static_preview.py tests/test_atlas_play_composite_runtime.py tests/test_atlas_play_process_sessions.py tests/test_atlas_play_environment_adapters.py tests/test_atlas_play_target_discovery.py tests/test_atlas_play_workspace_policy.py tests/test_atlas_play_portal_capsule_ppc0_contracts.py` -> 81 passed, 1 skipped.

Safety invariants verified:
- Portal runtime does not directly import subprocess or call Popen.
- Stored package hash tampering fails before staging.
- Untrusted imported package run is blocked by default.
- Portal purge removes disposable staged application content.
- Launch adapter policy remains separate from verification allowlists and does not alter workflow_state, PlanPool approval or self-apply authority.

Known limitations:
- Persistent data commit/snapshot lifecycle remains PR-PPC-10.
- Portal Preview/Logs/Stop UI wiring is API-ready but still minimal.

Remaining gaps:
- PR-PPC-10 Portal persistent data, discard and snapshots.

Next package:
PR-PPC-10 - Portal persistent data, discard and snapshots.

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
