# Atlas Play / Capsule / Portal Current Status

> Mutable checkpoint for Codex or Claude goal mode.
> Update this file after every work package.

## Goal status

- Overall: Planned / not implemented
- Baseline: `8d6897fe366a3877808f040a8828729350b89b7e`
- Canonical goal: `docs/atlas_play_portal_capsule_goal.md`
- Atlas Play specification: `docs/atlas_play_spec.md`
- Capsule and Portal specification: `docs/atlas_capsule_portal_spec.md`
- Canonical plan: `docs/atlas_play_portal_capsule_implementation_plan.md`
- Current work package: PR-PPC-0
- Next action: implement contracts, state reducers, path layout, limits and contract tests

## Baseline observations

- Atlas already has an isolated project working directory under `ca_data/atlas/projects/<name>/work`.
- Atlas project APIs already list, create, delete, persist conversation and download a development archive.
- The Atlas conversational shell is the visible Atlas UI; the legacy dashboard remains hidden for compatibility.
- The project picker and Plan History button are injected from `web/js/app.js` into `.atlas-claude-header-actions`.
- Atlas intent classification is implemented in `web/js/atlas_claude_panel.js` and currently recognizes `/plan`, not `/play`.
- Router registration is centralized in `app/server.py`.
- Safe Apply already validates relative targets under a workspace root; Play requires a broader shared read/write/execute/serve policy without weakening Safe Apply.
- No Portal top-level mode, Play session runtime, Capsule package contract or Portal data lifecycle exists yet.

## Work package table

| Package | Title | Status | Evidence |
|---|---|---|---|
| PR-PPC-0 | Baseline, contracts and threat model | Not started | - |
| PR-PPC-1 | Workspace access policy and file service | Not started | - |
| PR-PPC-2 | Play target and dependency discovery | Not started | - |
| PR-PPC-3 | Environment resolver and launch adapters | Not started | - |
| PR-PPC-4 | Process supervisor and Play sessions | Not started | - |
| PR-PPC-5 | Preview gateway and browser evidence | Not started | - |
| PR-PPC-6 | Atlas Play mobile workspace and controls | Not started | - |
| PR-PPC-7 | Capsule analysis and builder | Not started | - |
| PR-PPC-8 | Portal catalog, import and export | Not started | - |
| PR-PPC-9 | Portal staging and shared runtime launch | Not started | - |
| PR-PPC-10 | Persistent data, discard and snapshots | Not started | - |
| PR-PPC-11 | Disconnect recovery and lifecycle hardening | Not started | - |
| PR-PPC-12 | Acceptance, security and mobile E2E | Not started | - |

## Safety checkpoint

No implementation in this documentation branch adds process execution, file serving, package extraction, Portal data writes or UI authority. Existing Atlas authority and safety gates are unchanged.

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
