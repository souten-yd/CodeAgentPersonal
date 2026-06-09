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
- Current work package: PR-PPC-4
- Next action: implement process supervisor, sessions, events and cleanup

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

PR-PPC-3 adds environment inspection, structured launch adapter construction, loopback-only port contracts and composite DAG validation. It does not start processes, mutate host environments, install dependencies, open ports, preview applications, extract packages, write Portal data or add UI authority. Existing Atlas workflow state, PlanPool, approval, critical-event, allowed-path, rollback and retry boundaries are unchanged.

## Latest completed package evidence

Completed package:
PR-PPC-3 - Environment resolver and structured launch adapters.

PR/commit:
PR #1619 package commit.

Changed files:
- `app/api/atlas_play.py`
- `app/atlas/play/environment.py`
- `tests/test_atlas_play_environment_adapters.py`
- `docs/atlas_play_portal_capsule_current_status.md`

Public contracts added or changed:
- Added versioned environment resolver, structured launch adapter, loopback port contract and composite validation models.
- Added `/api/atlas/play/environment/resolve` endpoint.

Behavior implemented:
- Python environment inspection prefers local `.venv`/`venv` interpreters and records missing local environment evidence without host mutation.
- Node environment inspection validates `package.json` and selects pnpm/yarn/npm from lockfile precedence.
- Structured adapters cover static web, Python script, ASGI, WSGI, Streamlit, Django, Node script, npm script, Vite, Next and composite profiles.
- Adapter argv is bounded and structured; disallowed shell-like args and environment keys fail closed.
- All port contracts are loopback-only and not directly exposed.
- Composite profile validation rejects unknown dependencies and cycles, and returns deterministic startup order.
- Missing entrypoints or package metadata return `missing_dependency`, not a fallback command.

Focused tests:
- `python -m pytest -q tests/test_atlas_play_environment_adapters.py` -> 7 passed.

Syntax checks:
- `python -m py_compile app\atlas\play\environment.py app\api\atlas_play.py` -> passed.

Affected tests:
- `python -m pytest -q tests/test_atlas_play_environment_adapters.py tests/test_atlas_play_target_discovery.py tests/test_atlas_play_workspace_policy.py tests/test_atlas_play_portal_capsule_ppc0_contracts.py` -> 32 passed, 1 skipped.

Safety invariants verified:
- Adapter construction is metadata-only and sets `execution_started=false`.
- Launch adapter policy remains separate from verification allowlists and does not alter workflow_state, PlanPool approval or self-apply authority.
- No process execution, dependency installation, preview gateway, package extraction, Portal data write, general shell endpoint or raw host-filesystem serving was added.

Known limitations:
- PR-PPC-3 resolves environment metadata and structured adapter argv only. It does not start processes, allocate real ports, install dependencies or verify runtime readiness.

Remaining gaps:
- PR-PPC-4 process supervisor, sessions, events and cleanup.

Next package:
PR-PPC-4 - Process supervisor, sessions, events and cleanup.

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
