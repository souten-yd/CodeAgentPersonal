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
- Current work package: PR-PPC-3
- Next action: implement environment resolver and structured launch adapters

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

PR-PPC-2 adds Play target resolution, launch candidate detection, static dependency graph discovery, latest target graph persistence and Atlas-only `/play` intent routing to target discovery. It does not add process execution, preview serving, package extraction, Portal data writes, general shell access or UI authority. Existing Atlas workflow state, PlanPool, approval, critical-event, allowed-path, rollback and retry boundaries are unchanged.

## Latest completed package evidence

Completed package:
PR-PPC-2 - Play target and dependency discovery.

PR/commit:
PR #1618 package commit.

Changed files:
- `app/api/atlas_play.py`
- `app/atlas/play/paths.py`
- `app/atlas/play/target_discovery.py`
- `web/js/atlas_claude_panel.js`
- `web/js/atlas_pipeline_api.js`
- `tests/test_atlas_play_target_discovery.py`
- `docs/atlas_play_portal_capsule_current_status.md`

Public contracts added or changed:
- Added versioned Play target discovery request/result, launch candidate and dependency graph contracts.
- Added `/api/atlas/play/target/resolve` endpoint.
- Added target graph persistence under `ca_data/atlas/play/target_graphs/<project>/latest.json`.
- Added `AtlasPipelineAPI.resolvePlayTarget()` client method and Atlas chat `/play` intent dispatch to target discovery.

Behavior implemented:
- Target resolution order supports explicit `/play <entrypoint>`, current editor path, selected file path, last target and detected candidates.
- Button and command sources share the same backend resolver contract.
- Candidate detection covers HTML, Python scripts/ASGI hints and `package.json` scripts for npm/Vite/Next.
- Static dependency discovery follows HTML scripts/styles/assets, JS imports/requires, CSS imports/URLs and local Python imports.
- Missing or unsafe dependencies are diagnostic evidence and are not allowed to escape the project root.
- Multiple candidates return a mobile-selection-ready payload instead of guessing.
- `/play` is classified before `/plan` in Atlas and no Lumen route/client is added.

Focused tests:
- `python -m pytest -q tests/test_atlas_play_target_discovery.py` -> 6 passed.

Syntax checks:
- `python -m py_compile app\atlas\play\target_discovery.py app\atlas\play\paths.py app\api\atlas_play.py` -> passed.
- `node --check web\js\atlas_claude_panel.js; node --check web\js\atlas_pipeline_api.js` -> passed.

Affected tests:
- `python -m pytest -q tests/test_atlas_play_target_discovery.py tests/test_atlas_play_workspace_policy.py tests/test_atlas_play_portal_capsule_ppc0_contracts.py tests/test_lumen_intent_contract.py` -> 29 passed, 1 skipped.

Safety invariants verified:
- `/play` remains Atlas-only and no Lumen parser or route was added.
- Target/dependency paths reuse the workspace access policy and fail closed outside project root.
- No process execution, preview gateway, package extraction, Portal data write, general shell endpoint or raw host-filesystem serving was added.

Known limitations:
- PR-PPC-2 discovers targets and dependencies only. It does not resolve runtimes, construct launch commands, start processes or preview applications.
- Static dependency parsing is intentionally conservative; unsupported dynamic references become diagnostics for later target/runtime work.

Remaining gaps:
- PR-PPC-3 environment resolver and structured launch adapters.

Next package:
PR-PPC-3 - Environment resolver and structured launch adapters.

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
