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
- Current work package: PR-PPC-1
- Next action: implement shared workspace access policy and safe file service

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
| PR-PPC-1 | Workspace access policy and file service | Not started | - |
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

PR-PPC-0 adds contracts, reducers, path layout helpers and GET-only capability routers. It does not add process execution, file serving, package extraction, Portal data writes, preview proxying or UI authority. Existing Atlas workflow state, PlanPool, approval, critical-event, allowed-path, rollback and retry boundaries are unchanged.

## Latest completed package evidence

Completed package:
PR-PPC-0 - Baseline, contracts and threat model.

PR/commit:
PR #1616 package commit.

Changed files:
- `app/atlas/play/__init__.py`
- `app/atlas/play/contracts.py`
- `app/atlas/play/state.py`
- `app/atlas/play/paths.py`
- `app/atlas/capsule/__init__.py`
- `app/atlas/capsule/contracts.py`
- `app/portal/__init__.py`
- `app/portal/contracts.py`
- `app/portal/paths.py`
- `app/api/atlas_play.py`
- `app/api/portal.py`
- `app/server.py`
- `tests/test_atlas_play_portal_capsule_ppc0_contracts.py`
- `docs/atlas_play_portal_capsule_goal.md`
- `docs/atlas_play_spec.md`
- `docs/atlas_capsule_portal_spec.md`
- `docs/atlas_play_portal_capsule_implementation_plan.md`
- `docs/atlas_play_portal_capsule_current_status.md`

Public contracts added or changed:
- Added versioned Play request, target, launch profile, environment, session view, lifecycle event, resource limit and threat model contracts.
- Added versioned Capsule manifest, build request, package record and data-policy contracts.
- Added versioned Portal installation, run, data commit and snapshot contracts.
- Added no-side-effect Play lifecycle reducer.
- Added Atlas Play and Portal path layout helpers with containment-safe identifiers.
- Added GET-only `/api/atlas/play/capabilities` and `/api/portal/capabilities` router placeholders.
- Reflected review corrections C1-C5/O1-O3/S1 into canonical docs, including PR-PPC-4b and PR-PPC-5a/5b split, Console naming and untrusted package default-run block.

Behavior implemented:
- Unknown launch kinds fail closed through typed schema validation.
- Free-form `command` fields are rejected by strict persisted/imported models.
- Composite launch profiles are structured dependency lists, not shell command fields.
- Untrusted imported Portal package runs are blocked by default; explicit override returns a warning that v1 is not OS-isolated.
- State transitions reject invalid backward transitions and terminal-state restarts.
- Router placeholders expose contract metadata only and no execution/import/export/file-serving methods.

Focused tests:
- `python -m pytest -q tests/test_atlas_play_portal_capsule_ppc0_contracts.py` -> 8 passed.

Syntax checks:
- `python -m py_compile app\atlas\play\__init__.py app\atlas\play\contracts.py app\atlas\play\state.py app\atlas\play\paths.py app\atlas\capsule\__init__.py app\atlas\capsule\contracts.py app\portal\__init__.py app\portal\contracts.py app\portal\paths.py app\api\atlas_play.py app\api\portal.py app\server.py` -> passed.

Affected tests:
- `python -m pytest -q tests/test_atlas_play_portal_capsule_ppc0_contracts.py tests/test_atlas_workflow_state_router_registration_contract.py tests/test_lumen_api_router_contract.py tests/test_projects_router_contract.py` -> 16 passed.

Safety invariants verified:
- No process execution, file serving, preview gateway, package extraction, Portal data write, general shell endpoint or raw host-filesystem serving was added.
- Play/Portal launch adapter contracts remain independent from verification allowlists and do not change workflow_state, PlanPool approval or self-apply authority.
- Untrusted package execution is blocked by default in the public contract.

Known limitations:
- PR-PPC-0 is contract-only. Runtime launch, workspace file access, preview, Capsule build and Portal package/data lifecycle remain unimplemented by design.
- OS-level isolation for untrusted packages is not implemented in v1; untrusted Run is default-blocked and requires explicit override with warning.

Remaining gaps:
- PR-PPC-1 shared workspace access policy and safe file service.

Next package:
PR-PPC-1 - Workspace access policy and file service.

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
