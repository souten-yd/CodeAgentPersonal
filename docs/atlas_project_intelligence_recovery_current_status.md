# Atlas Project Intelligence Recovery — Current Status

## Program state

- Overall: **ACTIVE — PRODUCTION LOOP INCOMPLETE**
- Foundation Track: `PI-0..PI-25` merged as contracts, components, and scaffolds
- Active corrective track: `PIR-0..PIR-15`
- Current package: `PIR-6`
- Next action: implement whole-project semantic graph and parser-backed frontend analysis
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
| PIR-3 | source snapshots and Twin refresh | acceptance_complete |
| PIR-4 | durable event and delivery integration | acceptance_complete |
| PIR-5 | verification ingest, context, impact, test selection | acceptance_complete |
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

```text
Work package: PIR-3 — Real project source snapshots and Twin refresh lifecycle
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/source_adapter.py — read-only ProjectSourceAdapter with workspace-safe
  root resolution, path-escape rejection, symlink/binary/oversize/file-count guards, dirty
  changed/deleted path detection, and parser manifest.
- agent/project_twin/project_identity.py — working-tree identity now includes bounded file
  content hashes so same-size dirty edits produce distinct source identities.
- agent/project_twin/contracts.py and store.py — TwinDelta carries source_commit,
  working_tree_hash, and parser_versions; SqliteProjectTwinStore persists them on revisions.
- agent/project_twin/module.py — concrete DigitalTwinModuleImpl opens real repositories by
  running static and behavioral analyzers behind the facade, persists last successful source
  build records, performs scoped incremental refresh, invalidates deleted stale facts, and
  retains the prior active revision on failed refresh.
- agent/project_twin/__init__.py — exports source snapshot adapter DTOs.
- tests/test_project_twin_source_adapter.py
- tests/test_project_twin_source_refresh_lifecycle.py
- tests/test_project_intelligence_recovery_baseline.py — PIR-3 remains represented in the
  active recovery status table; later-package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_twin/contracts.py agent/project_twin/store.py
  agent/project_twin/project_identity.py agent/project_twin/source_adapter.py
  agent/project_twin/module.py agent/project_twin/__init__.py
  tests/test_project_twin_source_adapter.py tests/test_project_twin_source_refresh_lifecycle.py
  -> compile OK
- python -m pytest -q tests/test_project_twin_source_adapter.py
  tests/test_project_twin_source_refresh_lifecycle.py tests/test_project_twin_module_durability.py
  tests/test_project_workspace_isolation.py -> 13 passed in 6.08s
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py
  tests/test_project_twin_source_adapter.py tests/test_project_twin_source_refresh_lifecycle.py
  tests/test_project_twin_module_durability.py tests/test_project_workspace_isolation.py ->
  21 passed, 3 xfailed in 18.93s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_twin_source_adapter.py
  tests/test_project_twin_source_refresh_lifecycle.py tests/test_project_twin_module_durability.py
  tests/test_project_workspace_isolation.py tests/test_project_twin_static_graph.py
  tests/test_project_twin_behavioral_graph.py tests/test_project_twin_store.py
  tests/test_project_intelligence_lifecycle.py tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py tests/test_project_intelligence_recovery_baseline.py ->
  67 passed, 3 xfailed in 27.19s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 438 passed, 3 xfailed in 43.29s
Unavailable checks: no external Atlas workspace restart process was required for PIR-3; restart
  persistence is covered by close/reopen of durable store plus last-build sidecar. Planner,
  Generator, Verification, and delivery-event cutover remain later PIR work.
Safety invariants checked: source adapter is read-only and rejects path escapes; concrete Twin
  remains behind the public facade; failed refresh returns degraded with the prior active
  revision; no PlanPool, Proposal, Safe Apply, Verification, command authority, rollout
  cutover, or legacy deletion behavior changed.
Migration/rollout state: production composition remains off by default; active/shadow concrete
  service now gets source-backed Twin behavior when called, but no consumer cutover performed.
Known limitations: restart-safe durable event projection, runtime verification ingest, deeper
  semantic/CFG/data-flow/resource graphs, and real Planner/PlanPool integration begin in PIR-4+.
Next package: PIR-4 — durable canonical event and delivery projection integration.
Blocker: none.
```

```text
Work package: PIR-4 — Durable canonical event and delivery projection integration
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/event_projection_store.py — durable SQLite event inbox, delivery nodes,
  delivery edges, diagnostics, full event payload retention, idempotent replay, poison state,
  workspace-isolated trace queries, and DurableDeliveryTraceProjector.
- agent/project_twin/event_bridge.py — in-memory compatibility projector is now workspace
  isolated; projection failure retry jobs include full event payloads; bridge/projector close
  hook added.
- agent/project_twin/module.py — concrete DigitalTwinModuleImpl projects canonical events
  through the event bridge and triggers source-backed refresh for workspace.changed and
  safe_apply.completed events when project_path is present.
- agent/project_intelligence/production_factory.py — production composition creates durable
  event_projection.sqlite3 and injects the durable bridge into the concrete Twin.
- agent/project_intelligence/coordinator.py — active record_apply_result and
  record_verification_result emit canonical ProjectEventEnvelope instances into the injected
  Twin facade without becoming mutation authority.
- tests/test_project_twin_durable_event_projection.py
- tests/test_project_intelligence_recovery_baseline.py — PIR-4 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_twin/event_bridge.py
  agent/project_twin/event_projection_store.py agent/project_twin/module.py
  agent/project_twin/__init__.py agent/project_intelligence/production_factory.py
  tests/test_project_twin_durable_event_projection.py -> compile OK
- python -m pytest -q tests/test_project_twin_durable_event_projection.py
  tests/test_project_intelligence_event_bridge.py tests/test_project_intelligence_rollout.py ->
  24 passed in 2.95s
- python -m pytest -q tests/test_project_twin_durable_event_projection.py
  tests/test_project_intelligence_event_bridge.py tests/test_project_intelligence_rollout.py
  tests/test_project_twin_source_refresh_lifecycle.py tests/test_project_twin_module_durability.py
  tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py -> 38 passed in 10.75s
- python -m pytest -q tests/test_project_twin_durable_event_projection.py
  tests/test_project_intelligence_event_bridge.py tests/test_project_intelligence_rollout.py
  tests/test_project_twin_source_refresh_lifecycle.py tests/test_project_twin_module_durability.py
  tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py tests/test_project_intelligence_recovery_baseline.py ->
  46 passed, 3 xfailed in 21.51s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 445 passed, 3 xfailed in 41.20s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
Unavailable checks: no live Atlas UI/operator flow was run; PIR-4 verifies the production
  Project Intelligence facade caller path and the concrete Twin ingest path. Direct producer
  call-site cutover in every legacy Atlas service remains migration work for later PIR packages.
Safety invariants checked: events are emitted after Project Intelligence apply/verification
  records, not before canonical writes; projection failures queue retry payloads and do not
  mutate PlanPool/Safe Apply/Verification canonical state; duplicate replay is idempotent;
  poison events are diagnosable and do not block later events; project/workspace isolation is
  enforced in durable projection tables.
Migration/rollout state: rollout remains off by default; active production composition has
  durable delivery projection available, but no legacy path deletion or broad consumer cutover.
Known limitations: real verification artifact normalization, source/Twin revision separation
  in reconciliation, context ranking, impact/test selection, and deeper graph precision begin
  in PIR-5+.
Next package: PIR-5 — real verification ingestion, reconciliation, context, impact, and test
  selection.
Blocker: none.
```

```text
Work package: PIR-5 — Real verification ingestion, reconciliation, context, impact, and test selection
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/runtime/collectors.py — pytest normalization preserves per-test coverage
  subjects and emits concrete plus legacy-compatible symbol refs.
- agent/project_twin/contracts.py, migrations.py, store.py — RuntimeObservation carries
  source_revision, persisted through a Twin store migration, with durable observation queries.
- agent/project_twin/static_graph.py — Python class/function/route facts persist source line
  ranges for targeted source excerpts.
- agent/project_twin/module.py — runtime ingest diagnoses stale source evidence; test
  selection and context evidence use durable observations and filter stale evidence; context
  includes bounded runtime/test items and source excerpts with manifest source revisions.
- tests/test_project_twin_verification_context.py
- tests/test_project_intelligence_runtime.py — stack-frame expectation aligned with concrete
  source-backed Twin refs.
- tests/test_project_intelligence_recovery_baseline.py — PIR-5 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_twin/contracts.py agent/project_twin/migrations.py
  agent/project_twin/store.py agent/project_twin/static_graph.py
  agent/project_twin/runtime/collectors.py agent/project_twin/module.py
  tests/test_project_twin_verification_context.py tests/test_project_intelligence_runtime.py ->
  compile OK
- python -m pytest -q tests/test_project_twin_verification_context.py
  tests/test_project_intelligence_runtime.py tests/test_project_twin_source_refresh_lifecycle.py
  tests/test_project_twin_store.py -> 31 passed in 5.99s
- python -m pytest -q tests/test_project_twin_verification_context.py
  tests/test_project_intelligence_runtime.py tests/test_project_twin_source_refresh_lifecycle.py
  tests/test_project_twin_store.py tests/test_project_twin_static_graph.py
  tests/test_project_twin_durable_event_projection.py tests/test_project_intelligence_event_bridge.py
  tests/test_project_intelligence_rollout.py tests/test_project_intelligence_recovery_baseline.py ->
  71 passed, 3 xfailed in 21.26s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_intelligence_query_context.py::test_impact_recommended_tests_from_coverage
  tests/test_project_twin_verification_context.py tests/test_project_intelligence_runtime.py ->
  14 passed in 2.84s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 449 passed, 3 xfailed in 43.08s
Unavailable checks: no live external pytest/playwright command execution was run in this
  package; the package verifies canonical normalized artifacts and Project Intelligence/Twin
  ingestion APIs. PIR-13 remains the real Greenfield E2E gate.
Safety invariants checked: unavailable observations remain unavailable; stale source evidence
  is diagnosed and not used for current test selection/context verification; per-test coverage
  is preserved; source and Twin revisions remain separate; context is bounded and manifests
  record overflow rather than pretending complete context.
Migration/rollout state: rollout remains off by default; active concrete Twin now supports
  runtime evidence and context/test-selection queries, but no legacy consumer cutover or
  legacy deletion was performed.
Known limitations: cross-module semantic precision, parser-backed frontend analysis, richer
  CFG/data-flow/resource graphs, and labeled precision/recall benchmark expansion continue
  in PIR-6/PIR-7/PIR-15.
Next package: PIR-6 — whole-project semantic graph and parser-backed frontend analysis.
Blocker: none.
```
