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
- Current work package: PR-PPC-6
- Next action: implement Atlas Play mobile workspace and controls

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
| PR-PPC-6 | Atlas Play mobile workspace and controls | Not started | - |
| PR-PPC-7 | Capsule analysis and builder | Not started | - |
| PR-PPC-8 | Portal catalog, import and export | Not started | - |
| PR-PPC-9 | Portal staging and shared runtime launch | Not started | - |
| PR-PPC-10 | Persistent data, discard and snapshots | Not started | - |
| PR-PPC-11 | Disconnect recovery and lifecycle hardening | Not started | - |
| PR-PPC-12 | Acceptance, security and mobile E2E | Not started | - |

## Safety checkpoint

PR-PPC-5b adds a reverse proxy gateway for active Play sessions with owned loopback ports, including HTTP, SSE and WebSocket forwarding. It does not expose `file://`, direct temporary ports, open-proxy target selection, dependency installation, package extraction, Portal data write or UI authority. Existing Atlas workflow state, PlanPool, approval, critical-event, allowed-path, rollback and retry boundaries are unchanged.

## Latest completed package evidence

Completed package:
PR-PPC-5b - Reverse proxy, WebSocket and SSE gateway.

PR/commit:
PR-PPC-5b package branch.

Changed files:
- `app/api/atlas_play.py`
- `app/atlas/play/proxy_gateway.py`
- `tests/test_atlas_play_proxy_gateway.py`
- `tests/test_atlas_play_portal_capsule_ppc0_contracts.py`
- `docs/atlas_play_portal_capsule_current_status.md`

Public contracts added or changed:
- Added `/api/atlas/play/proxy/{session_id}/...` HTTP/SSE reverse proxy endpoints.
- Added `/api/atlas/play/proxy/{session_id}/ws/{path}` WebSocket forwarding.
- Capabilities now report preview gateway enabled.

Behavior implemented:
- HTTP proxy targets are derived only from the active session record's loopback port.
- Query-based proxy target injection keys fail closed.
- Host and origin/referer validation reject non-local proxy requests.
- Redirect `Location` headers are rewritten back through the session proxy path.
- Cookie paths are contained to the session proxy path.
- SSE streams are forwarded through bounded streaming responses.
- WebSocket text and binary messages are forwarded to the owned loopback session port.

Focused tests:
- `python -m pytest -q tests/test_atlas_play_proxy_gateway.py` -> 6 passed.

Syntax checks:
- `python -m py_compile app\atlas\play\proxy_gateway.py app\api\atlas_play.py tests\test_atlas_play_proxy_gateway.py tests\test_atlas_play_portal_capsule_ppc0_contracts.py` -> passed.

Affected tests:
- `python -m pytest -q tests/test_atlas_play_proxy_gateway.py tests/test_atlas_play_static_preview.py tests/test_atlas_play_composite_runtime.py tests/test_atlas_play_process_sessions.py tests/test_atlas_play_environment_adapters.py tests/test_atlas_play_target_discovery.py tests/test_atlas_play_workspace_policy.py tests/test_atlas_play_portal_capsule_ppc0_contracts.py` -> 58 passed, 1 skipped.

Safety invariants verified:
- Proxy targets are session-derived and cannot be supplied by request query or path.
- Cross-session port access and non-local host/origin requests fail closed.
- Redirect and cookie headers are rewritten or contained to the session proxy path.
- No arbitrary command or shell API was added.
- Launch adapter policy remains separate from verification allowlists and does not alter workflow_state, PlanPool approval or self-apply authority.

Known limitations:
- Gateway path/base rewriting is intentionally minimal and covered for redirects/cookies; richer app-specific base rewriting remains later hardening.
- Browser UI wiring remains later work.

Remaining gaps:
- PR-PPC-6 Atlas Play mobile workspace and controls.

Next package:
PR-PPC-6 - Atlas Play mobile workspace and controls.

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
