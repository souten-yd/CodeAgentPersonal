# Atlas Play / Capsule / Portal Current Status

> Mutable checkpoint for Codex or Claude goal mode.
> Update this file after every work package.

## Goal status

- Overall: Completed through PR-PPC-12
- Baseline: `8d6897fe366a3877808f040a8828729350b89b7e`
- Canonical goal: `docs/atlas_play_portal_capsule_goal.md`
- Atlas Play specification: `docs/atlas_play_spec.md`
- Capsule and Portal specification: `docs/atlas_capsule_portal_spec.md`
- Canonical plan: `docs/atlas_play_portal_capsule_implementation_plan.md`
- Current work package: Complete
- Next action: monitor CI and address review feedback if any

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
| PR-PPC-10 | Persistent data, discard and snapshots | Completed | `python -m pytest -q tests/test_portal_data_lifecycle.py` -> 7 passed; affected Portal/Capsule/Play slice -> 88 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-11 | Disconnect recovery and lifecycle hardening | Completed | `python -m pytest -q tests/test_portal_recovery_lifecycle.py` -> 6 passed; affected Portal/Capsule/Play slice -> 94 passed, 1 skipped; `python -m py_compile ...` -> passed |
| PR-PPC-12 | Acceptance, security and mobile E2E | Completed | `python -m pytest -q tests/test_atlas_play_portal_capsule_acceptance.py` -> 8 passed; affected Portal/Capsule/Play slice -> 102 passed, 1 skipped; `python -m py_compile ...`, `node --check ...` and Python Playwright iPhone viewport smoke -> passed |

## Safety checkpoint

PR-PPC-12 adds final acceptance/security coverage and enables structured ASGI, Node and Vite/NPM launch adapter kinds through the existing Play supervisor. It does not add a free-form command endpoint, include runtime data in Package Export, expose direct temporary ports, add a second Portal process runner, mutate immutable package archives or change workflow_state / PlanPool authority. Existing Atlas workflow state, approval, critical-event, allowed-path, rollback and retry boundaries are unchanged.

## Latest completed package evidence

Completed package:
PR-PPC-12 - Acceptance, security and mobile E2E.

PR/commit:
PR-PPC-12 package branch.

Changed files:
- `app/atlas/play/sessions.py`
- `tests/test_atlas_play_portal_capsule_acceptance.py`
- `tests/test_atlas_play_process_sessions.py`
- `docs/atlas_play_portal_capsule_current_status.md`

Public contracts added or changed:
- Play supervisor now accepts structured ASGI, Node script and Vite/NPM/Next adapter kinds that already satisfy launch adapter readiness, loopback and workspace checks.
- Added an end-to-end acceptance/security suite covering Play, Capsule, Portal, data lifecycle, recovery and quarantine matrix scenarios.
- Existing deferred-kind API test now verifies a still-unsupported structured kind (`streamlit`) remains blocked.
- Python Playwright iPhone-size viewport smoke is recorded for `ui.html` script loading and horizontal overflow.

Behavior implemented:
- Static HTML with nested CSS/JS/assets serves through session preview.
- Python script success output and failure handoff are captured.
- ASGI app preview works through the reverse proxy including SSE and WebSocket.
- Mobile file read/write/restart flow stays within the allowed project work root and rejects traversal.
- Play success can produce a multi-profile Capsule, Portal catalog reads it and Package Export remains data-free.
- Import quarantine rejects unsafe archive paths.
- Portal run data save, next-run continuity, snapshot start/discard and ephemeral expiry are covered.
- Fork to Atlas extracts immutable package content into a separate editable project work root.
- Stop/restart/failure paths release ports and remove staged runtime roots in the covered scenarios.

Focused tests:
- `python -m pytest -q tests/test_atlas_play_portal_capsule_acceptance.py` -> 8 passed.

Syntax checks:
- `python -m py_compile app\atlas\play\sessions.py tests\test_atlas_play_portal_capsule_acceptance.py` -> passed.
- `node --check web\js\atlas_play_workspace.js; node --check web\js\app.js; node --check web\js\atlas_pipeline_api.js` -> passed.
- Python Playwright iPhone viewport smoke (`390x844`, `ui.html`) -> `hasPlayScript=True`, `hasApiScript=True`, `bodyOverflowX=False`.

Affected tests:
- `python -m pytest -q tests/test_atlas_play_portal_capsule_acceptance.py tests/test_portal_recovery_lifecycle.py tests/test_portal_data_lifecycle.py tests/test_portal_runtime.py tests/test_portal_catalog.py tests/test_atlas_capsule_builder.py tests/test_atlas_play_mobile_workspace_ui_contract.py tests/test_atlas_play_proxy_gateway.py tests/test_atlas_play_static_preview.py tests/test_atlas_play_composite_runtime.py tests/test_atlas_play_process_sessions.py tests/test_atlas_play_environment_adapters.py tests/test_atlas_play_target_discovery.py tests/test_atlas_play_workspace_policy.py tests/test_atlas_play_portal_capsule_ppc0_contracts.py` -> 102 passed, 1 skipped.

Safety invariants verified:
- ASGI/Node/Vite support uses structured adapter argv only; free-form shell commands remain unsupported.
- Proxy scenario covers loopback session-owned ASGI HTTP/SSE/WebSocket rather than direct temporary port exposure.
- Package Export excludes current, snapshot and session data.
- Import quarantine unsafe path matrix fails closed.
- Workspace traversal is rejected in mobile file edit flow.
- Streamlit remains deferred as an unsupported v1 kind.
- Launch adapter policy remains separate from verification allowlists and does not alter workflow_state, PlanPool approval or self-apply authority.

Known limitations:
- Full live Vite dev-server execution was not run because the acceptance fixture does not install npm dependencies; structured Vite/NPM adapter generation and supervisor dispatch are covered.
- Runpod self-hosted GPU smoke can be skipped by CI availability; do not treat skipped platform jobs as local execution evidence.

Remaining gaps:
- None for the PR-PPC-0 through PR-PPC-12 work packages.

Next package:
Complete. Monitor PR/CI and address review feedback if any.

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
