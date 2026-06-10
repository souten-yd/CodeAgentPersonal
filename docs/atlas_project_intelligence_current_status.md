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
- Current work package: `PI-3` (PI-0, PI-1, PI-2 completed)
- Next action: composition root and rollout model (PI-3)
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
| PI-1 | Module facade contracts and boundary tests | Completed | 4 module facades + contracts; `tests/test_project_intelligence_contracts.py`+`_boundaries.py` → 28 passed; affected suite 199 passed |
| PI-2 | Persistence and migration foundation | Completed | isolated SQLite stores (blueprint/convergence/PI) + migrations; `tests/test_project_intelligence_persistence.py` → 12 passed; affected 107 passed |
| PI-3 | Composition root and rollout model | In Progress | current package |
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
Work package: PI-2 — Persistence and migration foundation
Status: Completed
Commit/PR: local branch pi-0-production-baseline (not pushed/merged)
Changed modules/files:
- agent/project_intelligence/_persistence.py (new) — shared, dependency-neutral SQLite
  kernel: connection factory, transactional/repeatable migration runner, generic immutable
  revisioned ArtifactStore (idempotency, stale-parent rejection, point-in-time, integrity).
- agent/architecture_blueprint/migrations.py, store.py (new) — immutable Blueprint revisions.
- agent/project_convergence/migrations.py, store.py (new) — immutable Convergence report history.
- agent/project_intelligence/migrations.py, store.py (new) — immutable Context Manifests +
  restart-safe job journal (enqueue/claim/complete/recover, ADR-PI-011).
- tests/test_project_intelligence_persistence.py (new)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Each module owns an isolated SQLite store behind its facade; SQLite stays an internal
  adapter (ADR-PI-015) — no public contract imports it (boundary test unchanged).
- Immutable revision rows; one put == one transaction with rollback; duplicate idempotency
  key is a harmless no-op; stale expected-parent is rejected; project/workspace isolation;
  point-in-time reads; integrity check returns ok/corrupt with diagnostics.
- Migrations are repeatable (IF NOT EXISTS + version guard) and rollback-safe (per-migration
  BEGIN/COMMIT/ROLLBACK; a failed migration is not recorded).
- No PlanPool/Conversation/Nexus/Memory canonical data is migrated or rewritten (ADR-PI-004).
Executed commands and exact results:
- python -m py_compile (7 new module files + test) -> compile OK
- python -m pytest -q tests/test_project_intelligence_persistence.py -> 12 passed in 0.63s
- python -m pytest -q boundaries+contracts+persistence+baseline+twin_baseline -> 107 passed in 2.45s
Unavailable checks: none required (in-memory + temp SQLite only).
Safety invariants checked: stores are advisory persistence; no workflow/PlanPool/approval/
  Safe Apply/rollback/retry/command/isolation/verification behavior touched; SQLite not
  exposed through any facade.
Migration/rollout state: persistence introduced; not yet wired to facades (PI-3 composition).
Known limitations: stores are standalone; the facades still return disabled results until
  PI-3 composition root + rollout wire them behind the rollout flag.
Next package: PI-3 — Composition root and rollout model.
Blocker: none.
```

```text
Work package: PI-1 — Module facade contracts and boundary tests
Status: Completed
Commit/PR: local branch pi-0-production-baseline (not pushed/merged)
Changed modules/files:
- agent/project_intelligence/__init__.py, contracts.py, facade.py (new)
- agent/project_twin/facade.py (new; atlas.digital_twin.v2 facade over Core v1)
- agent/architecture_blueprint/__init__.py, contracts.py, facade.py (new)
- agent/project_convergence/__init__.py, contracts.py, facade.py (new)
- tests/test_project_intelligence_contracts.py, tests/test_project_intelligence_boundaries.py (new)
- tests/test_project_intelligence_baseline.py (PI-0 absence pin flipped to presence pin)
- docs/atlas_project_intelligence_current_status.md (this file)
Behavior implemented:
- Versioned public contracts for four families: atlas.project_intelligence.v1,
  atlas.digital_twin.v2, atlas.architecture_blueprint.v1, atlas.project_convergence.v1.
- Four coarse-grained facade Protocols (DigitalTwinModule, ArchitectureBlueprintModule,
  ConvergenceModule, ProjectIntelligenceModule) + shared contract kernel (ProjectIdentity,
  ContextManifest, ContextItem, SourceExcerpt, RuntimeObservationRecord, ProjectMode,
  typed IntelligenceErrorCode/IntelligenceError).
- Disabled-by-default concrete stubs for all four facades: explicit DISABLED/unavailable
  results; never fabricate twin revisions, blueprints, convergence completion, or passed
  observations; unavailable observations stay unavailable (ADR-PI-013); blueprint
  activate/get_revision raise typed errors instead of fabricating a revision.
- v1 compatibility readers: accepts_twin_contract_version (reads atlas.project_twin.v1
  and v2); context_item_from_v1_slice_item adapts a Core v1 context item without upgrading
  status/confidence.
- Dependency direction enforced: PI facade -> twin/blueprint/convergence facades; twin and
  blueprint independent; portable cores import only stdlib/typing/pydantic + shared kernel.
  PI package __init__ exports the coordinator lazily (PEP 562) to keep the kernel import
  cycle-free.
Executed commands and exact results:
- python -m py_compile (10 new module files + 2 new tests) -> compile OK
- python -m pytest -q tests/test_project_intelligence_contracts.py
  tests/test_project_intelligence_boundaries.py -> 28 passed in 1.06s
- python -m pytest -q tests/test_project_intelligence_baseline.py + contracts + boundaries
  + tests/test_project_twin_*.py -> 199 passed in 7.30s
Unavailable checks: none required (no runtime/browser instrumentation in PI-1).
Safety invariants checked: facades are advisory/disabled; no PlanPool/approval/Safe Apply/
  rollback/retry/command/isolation/verification behavior touched; no facade exposes a private
  store; no portable core imports FastAPI/app.api/PlanPool/SQLite (AST boundary test).
Migration/rollout state: facades introduced disabled; no consumer cutover; no legacy deletion.
Known limitations: facades are stubs — open/refresh/query/build_context/create/evaluate
  return disabled results. Real persistence (PI-2), composition/rollout (PI-3) and Digital
  Twin production wiring (PI-4+) are later packages.
Next package: PI-2 — Persistence and migration foundation.
Blocker: none.
```

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
