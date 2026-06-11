# Atlas Portal + Model Forge — Current Status

> Mutable checkpoint for Codex or Claude goal mode.
> Update this file after every coherent work package.

## Program state

- Overall: **ACTIVE — DESIGN CHECKPOINT ONLY**
- Active track: `PFG-0..PFG-38`
- Current package: `PFG-0`
- Current package goal: land canonical Portal + Model Forge docs and AGENTS.md entrypoint.
- Next action after PFG-0: start `PFG-1` Portal polish audit and compatibility gates.
- Portal baseline: PR-PPC-0 through PR-PPC-12 are complete; Portal UI reconciliation has wired Portal navigation/catalog/run/data decisions into the production shell.
- Project Intelligence baseline: PIR remains active separately. Do not delete or override PIR instructions.
- Rollout: Forge off by default; legacy model execution remains primary until shadow/cutover gates pass.

This file selects the active Portal + Model Forge package. Do not use this status file to claim PIR completion.

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_portal_forge_master_goal.md`
3. `docs/atlas_portal_forge_current_status.md`
4. current package in `docs/atlas_portal_forge_implementation_plan.md`
5. relevant sections of `docs/atlas_portal_forge_detailed_design.md`
6. relevant sections of `docs/atlas_portal_forge_test_plan.md`
7. Portal/Capsule baseline docs:
   - `docs/atlas_play_portal_capsule_current_status.md`
   - `docs/atlas_play_portal_capsule_goal.md`
   - `docs/atlas_capsule_portal_spec.md`
8. Project Intelligence recovery docs when touching Atlas/PIR/PlanPool/Proposal/Safe Apply/Verification/Convergence paths:
   - `docs/atlas_project_intelligence_recovery_current_status.md`
   - `docs/atlas_project_intelligence_recovery_master_goal.md`
9. target code, direct callers, dependencies, and tests.

## Confirmed baseline

- Portal top-level navigation exists.
- Portal catalog/run sheet exists.
- Portal data lifecycle includes Save, Snapshot, Discard, backup/delete, heartbeat/disconnect/resume.
- Capsule builder is wired through the UI and calls `buildCapsule`.
- Portal run uses public Portal runtime API, not a second process runner.
- Package Export remains data-free.
- Free-form command execution remains unsupported.
- Portal has known polish gaps:
  - browser upload import endpoint/UI;
  - snapshot-list/start-from-snapshot run selector;
  - legacy package manifest sidecar repair;
  - Forge Trace panel and Portal x Forge metadata.

## Package table

| Package | Goal | Status |
|---|---|---|
| PFG-0 | baseline and design acceptance | in_progress |
| PFG-1 | Portal polish audit and compatibility gates | not_started |
| PFG-2 | Portal import upload endpoint and UI | not_started |
| PFG-3 | Portal snapshot listing and start-from-snapshot UI | not_started |
| PFG-4 | legacy package manifest sidecar repair | not_started |
| PFG-5 | Forge core schemas and taxonomies | not_started |
| PFG-6 | provider base and registry | not_started |
| PFG-7 | Legacy Atlas Executor adapter | not_started |
| PFG-8 | local OpenAI-compatible provider adapter | not_started |
| PFG-9 | OpenRouter configuration and secret policy | not_started |
| PFG-10 | OpenRouter mock chat client | not_started |
| PFG-11 | OpenRouter model catalog cache | not_started |
| PFG-12 | provider health and Source Mode policy | not_started |
| PFG-13 | benchmark preset schema and initial presets | not_started |
| PFG-14 | Arena runner foundation | not_started |
| PFG-15 | Candidate Evaluator foundation | not_started |
| PFG-16 | Model Profile Store and profile updater | not_started |
| PFG-17 | Stage Matrix policy and selector | not_started |
| PFG-18 | Route Matrix policy and selector | not_started |
| PFG-19 | Forge backend API | not_started |
| PFG-20 | Forge top-level nav and shell UI | not_started |
| PFG-21 | Forge Overview and Provider cards | not_started |
| PFG-22 | Skill Radar and Leaderboard UI | not_started |
| PFG-23 | Benchmark Preset selector UI | not_started |
| PFG-24 | Arena UI | not_started |
| PFG-25 | Stage Matrix and Route Matrix UI | not_started |
| PFG-26 | Loadouts UI and persistence | not_started |
| PFG-27 | Portal Run Forge Trace metadata | not_started |
| PFG-28 | Portal evidence to Candidate Evaluator | not_started |
| PFG-29 | Capsule Forge metadata and replay | not_started |
| PFG-30 | real local-model Quick preset run | not_started |
| PFG-31 | real Web App / Portal run preset | not_started |
| PFG-32 | real Repair preset run | not_started |
| PFG-33 | real Greenfield Capsule replay run | not_started |
| PFG-34 | optional OpenRouter live smoke gate | not_started |
| PFG-35 | stage shadow evidence for patch/test/failure/repair | not_started |
| PFG-36 | controlled Forge primary cutover for selected stage | not_started |
| PFG-37 | legacy retirement gates and consumer registry | not_started |
| PFG-38 | final milestone benchmark and docs | not_started |

## Status values

Use only:

```text
not_started
in_progress
component_complete
production_connected
acceptance_complete
blocked
```

## Completion rule

Portal + Model Forge remains incomplete until PFG-38 and every required live/model/Portal/rollout gate in `docs/atlas_portal_forge_master_goal.md` pass.

Do not mark the program complete from:

- docs alone;
- mock provider tests alone;
- adapter-only tests;
- UI rendering alone;
- manually supplied metrics;
- unavailable live model/OpenRouter checks.

## Executed package log

```text
Work package: PFG-0 — Baseline and design acceptance
Status: in_progress
Changed modules/files:
- docs/atlas_portal_forge_master_goal.md — added the Portal + Model Forge product and evidence goal.
- docs/atlas_portal_forge_detailed_design.md — added architecture, schema, provider, Portal x Forge, UI, and rollout design.
- docs/atlas_portal_forge_implementation_plan.md — added PFG-0..PFG-38 sequential package plan.
- docs/atlas_portal_forge_test_plan.md — added PIR-style test/evidence plan.
- docs/atlas_portal_forge_current_status.md — added this active checkpoint.
Pending modules/files:
- docs/atlas_portal_forge_agent_entrypoint.md
- AGENTS.md
Public contracts added or changed:
- Documentation only so far; no runtime behavior change.
Behavior implemented:
- None.
Focused tests:
- Not yet run; docs-only checkpoint.
Syntax checks:
- Not yet run; docs-only checkpoint.
Affected tests:
- Not yet run; docs-only checkpoint.
Real model / Portal / OpenRouter evidence:
- None claimed.
Unavailable checks:
- No live model, Portal runtime, or OpenRouter execution claimed in PFG-0.
Safety invariants verified:
- Design requires no free-form command execution, no direct Arena apply, no secret persistence, no unavailable-as-passed, no legacy retirement without gates.
Migration/rollout state:
- Forge off by default; legacy model execution remains primary.
Known limitations:
- PFG implementation has not started.
Remaining gaps:
- Finish agent entrypoint and AGENTS.md update for PFG-0.
Next package:
- PFG-1 — Portal polish audit and compatibility gates.
Blocker:
- None.
```

## Update template

After each package record:

```text
Completed package:
Status:
Changed modules/files:
Public contracts added or changed:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Real model / Portal / OpenRouter evidence:
Unavailable checks:
Safety invariants verified:
Migration/rollout state:
Known limitations:
Remaining gaps:
Next package:
Blocker:
```
