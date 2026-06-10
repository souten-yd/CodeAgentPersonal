# Atlas Project Intelligence Recovery — Current Status

## Program state

- Overall: **ACTIVE — PRODUCTION LOOP INCOMPLETE**
- Foundation Track: `PI-0..PI-25` merged as contracts, components, and scaffolds
- Active corrective track: `PIR-0..PIR-15`
- Current package: `PIR-3`
- Next action: implement real project source snapshots and Twin refresh lifecycle
- Blocker: none
- Rollout: off by default

This file selects the active package. The old PI package table does not prove final completion.

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_project_intelligence_recovery_master_goal.md`
3. `docs/atlas_project_intelligence_pi0_25_implementation_audit.md`
4. this file
5. current package in `docs/atlas_project_intelligence_recovery_implementation_plan.md`
6. relevant recovery detailed-design and test-plan sections
7. existing Project Intelligence decisions, contracts, and architecture
8. target code, direct callers, dependencies, and tests

## Confirmed gaps

- production composition uses disabled modules;
- coordinator active paths do not return real module output;
- concrete Twin and Convergence facades are missing;
- new Planner, Generator, and Verification adapters are not connected to real Atlas consumers;
- durability defects remain in Blueprint, event projection, and checkpoints;
- CFG, data flow, frontend semantics, and resource graphs are incomplete;
- Convergence revision and completion logic require correction;
- Plan Compiler is not authoritative PlanPool integration;
- Greenfield E2E and final benchmark are synthetic;
- live rollout, platform evidence, consumer cutover, and retirement are incomplete.

## Package table

| Package | Goal | Status |
|---|---|---|
| PIR-0 | baseline, inventory, regression locks | acceptance_complete |
| PIR-1 | durable concrete modules | acceptance_complete |
| PIR-2 | production composition and rollout preflight | acceptance_complete |
| PIR-3 | source snapshots and Twin refresh | not_started |
| PIR-4 | durable event and delivery integration | not_started |
| PIR-5 | verification ingest, context, impact, test selection | not_started |
| PIR-6 | whole-project semantic graph | not_started |
| PIR-7 | CFG, data flow, state/event/resource graphs | not_started |
| PIR-8 | durable Blueprint planning and review | not_started |
| PIR-9 | Convergence correctness and evidence policy | not_started |
| PIR-10 | Planner and PlanPool production integration | not_started |
| PIR-11 | Proposal, Safe Apply, and refresh integration | not_started |
| PIR-12 | Verification, recovery, checkpoint, resume | not_started |
| PIR-13 | real Greenfield E2E | not_started |
| PIR-14 | CI, platform, scale, and consumer cutover | not_started |
| PIR-15 | real benchmark and retirement | not_started |

## Status values

```text
not_started
in_progress
component_complete
production_connected
acceptance_complete
blocked
```

Do not use plain `Completed` without the proof level. Focused tests alone cannot close a package requiring production or live evidence.

## Completion rule

The program remains incomplete until PIR-15 and every live Definition of Done gate in the recovery master goal pass. Synthetic runners, manually supplied metrics, adapter-only tests, and document statements are not production evidence.

## Executed package log

```text
Work package: PIR-0 — Truthful baseline, executable inventory, and regression locks
Status: acceptance_complete
Changed modules/files:
- agent/project_intelligence/inspection/consumer_inventory.py — AST-based production entrypoint,
  legacy consumer, facade/adapter, construction-site, module implementation, and persistence
  default inventory generator.
- tools/generate_project_intelligence_consumer_inventory.py — CLI for regenerating the inventory.
- docs/generated/atlas_project_intelligence_consumer_inventory.json — generated artifact from
  the current checkout.
- tests/test_project_intelligence_recovery_baseline.py — PIR-0 inventory assertions plus strict
  xfail regression locks for audited defects PIR0-C01..PIR0-C07.
- docs/atlas_project_intelligence_current_status.md — PI-0..PI-25 reframed as Foundation Track.
Executed commands and exact results:
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=31 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m py_compile agent/project_intelligence/inspection/consumer_inventory.py
  tools/generate_project_intelligence_consumer_inventory.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py ->
  5 passed, 6 xfailed in 16.30s
- python -m pytest -q tests/test_project_intelligence_baseline.py
  tests/test_project_intelligence_contracts.py tests/test_project_intelligence_rollout.py
  tests/test_project_intelligence_recovery_baseline.py -> 74 passed, 6 xfailed in 18.44s
- $files = Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName };
  python -m pytest -q @files -> 291 passed, 6 xfailed in 30.20s
Unavailable checks: none for PIR-0; no production behavior change or live environment claim.
Safety invariants checked: read-only source inspection only; no production runtime, PlanPool,
  Proposal, Safe Apply, verification, rollout, or legacy path behavior changed.
Migration/rollout state: off by default; no consumer cutover and no legacy deletion.
Known limitations: regression locks intentionally xfail until PIR-1+ fixes the underlying defects.
Next package: PIR-1 — durable concrete modules.
Blocker: none.
```

```text
Work package: PIR-1 — Durable concrete module foundations
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/module.py — concrete DigitalTwinModuleImpl over the durable Twin store,
  workspace-isolated by internal project key, with open/refresh/rebuild/event/runtime/query/
  context/health facade methods.
- agent/project_convergence/module.py — concrete ConvergenceModuleImpl over ConvergenceStore,
  with injectable Blueprint/Actual/verification loaders, persisted reports, and persisted
  bounded decisions.
- agent/architecture_blueprint/module.py and store.py — durable lifecycle status updates
  and deterministic get_active per project/workspace after reopen.
- agent/project_intelligence/_persistence.py, project_twin/store.py, project_intelligence/store.py,
  project_intelligence/checkpoint.py, project_convergence/store.py — file-backed defaults for
  concrete persistence; explicit test-supplied SQLite memory remains available.
- tests/test_project_intelligence_facade_conformance.py
- tests/test_project_twin_module_durability.py
- tests/test_blueprint_durable_lifecycle.py
- tests/test_convergence_module_durability.py
- tests/test_project_workspace_isolation.py
- tests/test_project_intelligence_recovery_baseline.py — PIR0-C04/C05/C06 locks now pass;
  remaining later-package locks stay strict xfail.
Executed commands and exact results:
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=31 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m py_compile agent/project_intelligence/_persistence.py agent/project_twin/store.py
  agent/project_twin/module.py agent/architecture_blueprint/module.py
  agent/project_convergence/module.py agent/architecture_blueprint/store.py
  agent/project_convergence/store.py agent/project_intelligence/store.py
  agent/project_intelligence/checkpoint.py tests/test_project_intelligence_facade_conformance.py
  tests/test_project_twin_module_durability.py tests/test_blueprint_durable_lifecycle.py
  tests/test_convergence_module_durability.py tests/test_project_workspace_isolation.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_facade_conformance.py
  tests/test_project_twin_module_durability.py tests/test_blueprint_durable_lifecycle.py
  tests/test_convergence_module_durability.py tests/test_project_workspace_isolation.py
  tests/test_project_intelligence_recovery_baseline.py -> 16 passed, 4 xfailed in 18.47s
- python -m pytest -q tests/test_project_intelligence_contracts.py
  tests/test_project_intelligence_persistence.py tests/test_project_intelligence_blueprint_lifecycle.py
  tests/test_project_intelligence_convergence_eval.py tests/test_project_intelligence_convergence_decision.py
  tests/test_project_twin_store.py tests/test_project_intelligence_facade_conformance.py
  tests/test_project_twin_module_durability.py tests/test_blueprint_durable_lifecycle.py
  tests/test_convergence_module_durability.py tests/test_project_workspace_isolation.py
  tests/test_project_intelligence_recovery_baseline.py -> 81 passed, 4 xfailed in 20.32s
- PowerShell-expanded project_intelligence + project_twin suites plus PIR-1 durability/isolation
  tests -> 427 passed, 4 xfailed in 38.53s
Unavailable checks: none required for PIR-1; production app composition begins in PIR-2.
Safety invariants checked: concrete modules remain behind public facades; no FastAPI/UI/app API/
  PlanPool imports in portable concrete modules; no production rollout/cutover/legacy deletion;
  explicit SQLite memory remains test-only when supplied by tests.
Migration/rollout state: rollout remains off by default; no consumer cutover.
Known limitations: Digital Twin source snapshots/analyzers and production construction are not
  wired until PIR-2/PIR-3; Convergence uses injected loaders until production composition supplies
  real Blueprint/Actual sources.
Next package: PIR-2 — production composition and rollout preflight.
Blocker: none.
```

```text
Work package: PIR-2 — Production composition root, service lifecycle, and rollout preflight
Status: acceptance_complete
Changed modules/files:
- agent/project_intelligence/production_factory.py — production composition root resolving
  durable module DBs under ca_data/project_intelligence, off-mode disabled compatibility,
  shadow/active concrete composition, persisted rollout state, and fail-closed preflight.
- agent/project_intelligence/service_registry.py — app.state lifecycle holder and shutdown close.
- app/api/atlas_project_intelligence.py and app/server.py — read-only health route under
  /api/atlas/project-intelligence/health.
- main.py — production lifespan registration/close for the Project Intelligence service.
- agent/project_intelligence/coordinator.py and factory.py — composition dependency types moved
  to public facade protocols.
- tests/test_project_intelligence_production_composition.py
- tests/test_project_intelligence_app_lifecycle.py
- tests/test_project_intelligence_rollout_preflight.py
- tests/test_project_intelligence_health_api.py
- tests/test_project_intelligence_recovery_baseline.py — PIR0-C01 production-composition lock
  now passes; remaining later-package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/coordinator.py
  agent/project_intelligence/factory.py agent/project_intelligence/production_factory.py
  agent/project_intelligence/service_registry.py app/api/atlas_project_intelligence.py
  app/server.py main.py tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py tests/test_project_intelligence_recovery_baseline.py ->
  15 passed, 3 xfailed in 16.15s
- python -m pytest -q tests/test_project_intelligence_rollout.py
  tests/test_project_intelligence_planner_bridge.py tests/test_project_intelligence_generator_bridge.py
  tests/test_project_intelligence_contracts.py tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py tests/test_project_intelligence_recovery_baseline.py ->
  50 passed, 3 xfailed in 17.47s
- PowerShell-expanded project_intelligence + project_twin suites plus PIR-1 durability/isolation
  tests -> 435 passed, 3 xfailed in 38.09s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py ->
  8 passed, 3 xfailed in 13.48s
Unavailable checks: production planner/generator/verification consumer cutover remains later
  PIR work; no behavior change is claimed for those consumers in PIR-2.
Safety invariants checked: off mode composes disabled modules and remains legacy-compatible;
  shadow/active compose concrete modules and fail closed on unusable stores; health endpoint
  returns no private rows; no Safe Apply, Proposal, Verification, PlanPool, or legacy deletion.
Migration/rollout state: rollout_state.json is persisted under ca_data/project_intelligence;
  rollback history is represented and preserved, but no phase cutover performed.
Known limitations: Project Intelligence service is registered and inspectable; real source
  snapshots and Twin refresh lifecycle begin in PIR-3.
Next package: PIR-3 — real project source snapshots and Twin refresh lifecycle.
Blocker: none.
```
