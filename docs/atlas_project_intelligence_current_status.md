# Atlas Project Intelligence — Current Status

> Mutable execution checkpoint for Codex goal mode.
> Update after every work package.
> Do not infer completion from design documents or old PDT status.

## Program status

- Overall: **ACTIVE — NOT COMPLETE**
- Completed foundation: Project Digital Twin Core v1, PDT-0 through PDT-14
- Active canonical goal: `docs/atlas_project_intelligence_master_goal.md`
- Architecture: `docs/atlas_project_intelligence_architecture.md`
- Detailed design: `docs/atlas_project_intelligence_detailed_design.md`
- Public contracts: `docs/atlas_project_intelligence_contracts.md`
- Detailed implementation plan: `docs/atlas_project_intelligence_implementation_plan.md`
- Test plan: `docs/atlas_project_intelligence_test_plan.md`
- Migration/reorganization plan: `docs/atlas_project_intelligence_migration_plan.md`
- Agent entrypoint: `docs/atlas_project_intelligence_agent_entrypoint.md`
- Current work package: `PI-1` (PI-0 completed)
- Next action: implement module facade contracts and boundary tests (PI-1)
- Blocker: none recorded
- Safety posture: existing Atlas authority, approval, Safe Apply, rollback, retry, command, project-isolation, and truthful-verification rules remain unchanged

## Important interpretation

The old `docs/atlas_project_digital_twin_current_status.md` records completion of PDT Core v1 only. It is a historical checkpoint and is not the active overall goal.

Current gaps include:

- production use of Digital Twin in real Planner/Generator/Verification paths;
- deep semantic/call/control-flow/data-flow/state/event/resource/runtime graphs;
- Architecture Blueprint Module;
- Convergence Module;
- Greenfield generation with build/run evidence;
- existing project-analysis/context/impact duplication consolidation;
- phased rollout and final comparative benchmark.

## Work package table

| WP | Title | Status | Evidence / Notes |
|---|---|---|---|
| PI-0 | Production baseline and consumer map | Completed | maps + `tests/test_project_intelligence_baseline.py` → 46 passed; twin baseline 21 passed; full twin+PI suites 171 passed |
| PI-1 | Module facade contracts and boundary tests | In Progress | current package |
| PI-2 | Persistence and migration foundation | Not Started | |
| PI-3 | Composition root and rollout model | Not Started | |
| PI-4 | Project identity, mode detection, lifecycle | Not Started | |
| PI-5 | Canonical event bridge and trace expansion | Not Started | |
| PI-6 | Static and semantic graph v2 | Not Started | |
| PI-7 | Behavioral graph v2 | Not Started | |
| PI-8 | Runtime intelligence and reconciliation v2 | Not Started | |
| PI-9 | Context, path, impact, test selection v2 | Not Started | |
| PI-10 | Blueprint model, store, lifecycle | Not Started | |
| PI-11 | Blueprint generation, review, validation | Not Started | |
| PI-12 | Blueprint-to-Actual mapping hints | Not Started | |
| PI-13 | Convergence matcher and evaluator | Not Started | |
| PI-14 | Convergence decision and incremental evaluation | Not Started | |
| PI-15 | Completion and requirement-evidence integration | Not Started | |
| PI-16 | Planning envelope and Plan Compiler | Not Started | |
| PI-17 | Planner production integration | Not Started | |
| PI-18 | Generator and repair integration | Not Started | |
| PI-19 | Verification, checkpoint, resume | Not Started | |
| PI-20 | Greenfield bootstrap orchestrator | Not Started | |
| PI-21 | Coherent multi-file generation | Not Started | |
| PI-22 | Greenfield build/run/test and real E2E | Not Started | |
| PI-23 | Capability consolidation and consumer cutover | Not Started | |
| PI-24 | Cross-platform, scale, storage, rollout hardening | Not Started | |
| PI-25 | Final benchmark and legacy retirement | Not Started | |

## Per-package update template

After each package, append or update:

```text
Work package:
Status:
Commit/PR:
Changed modules/files:
Executed commands and exact results:
Unavailable checks:
Safety invariants checked:
Migration/rollout state:
Known limitations:
Next package:
Blocker, if any:
```

## Executed package log

```text
Work package: PI-0 — Production baseline and consumer map
Status: Completed
Commit/PR: local branch pi-0-production-baseline (not pushed/merged)
Changed modules/files:
- docs/atlas_project_intelligence_existing_capability_map.md (new)
- docs/atlas_project_intelligence_consumer_map.md (new)
- docs/atlas_project_intelligence_migration_matrix.md (new)
- tests/test_project_intelligence_baseline.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Read-only executable baseline of project-analysis/context/impact/verification-support
  and Project Twin Core v1 capabilities against current main (HEAD 0fd98c1).
- existing_capability_map: owners by symbol, duplication, reusable contracts, missing
  behavior, migration risk (capability inventory §4; duplication §6).
- consumer_map: direct consumers by symbol for every owner; recorded that the Twin Core v1
  has exactly one production consumer today (app/api/project_twin.py, read-only) — the
  central production-wiring gap; pipeline + repo_context APIs are the principal orchestrators.
- migration_matrix: validated + expanded migration_plan §4; KEEP/ADAPT/REPLACE/REMOVE for
  every owner + net-new modules, with PI destination and retirement gate per row.
- baseline test pins: owner importability + owner symbols present; deterministic CodeIntel
  symbol/dependency output; Code Explorer duplication present; HybridMemory long-scope
  no-op without saver; Twin Core v1 contracts (atlas.project_twin.v1) present; ABSENCE of
  the four PI module packages (PI-1 introduces them); PDT Core v1 recorded complete and
  the PI program recorded ACTIVE at PI-0.
Executed commands and exact results:
- python -m py_compile tests/test_project_intelligence_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_baseline.py -> 46 passed in 0.85s
- python -m pytest -q tests/test_project_twin_baseline.py -> 21 passed in 0.84s
- python -m pytest -q tests/test_project_twin_*.py tests/test_project_intelligence_baseline.py
  -> 171 passed in 6.96s
Unavailable checks: none required for PI-0 (no runtime/browser instrumentation involved).
Safety invariants checked: no production code changed; no workflow/PlanPool/approval/
  Safe Apply/rollback/retry/command-allowlist/isolation/verification behavior touched
  (docs + read-only test only).
Migration/rollout state: classification recorded; no cutover, no deletion, no rollout change.
Known limitations: maps are descriptive; the four module facades do not exist yet (PI-1).
Next package: PI-1 — Module facade contracts and boundary tests.
Blocker: none.
```

## Completion rule

Do not mark the program COMPLETE until PI-25 and all final Definition of Done conditions pass. Individual modules may be complete earlier, but production integration, real E2E, reorganization, rollout, and comparative benchmark are mandatory parts of the goal.
