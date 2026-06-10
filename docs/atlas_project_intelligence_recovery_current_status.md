# Atlas Project Intelligence Recovery — Current Status

## Program state

- Overall: **ACTIVE — PRODUCTION LOOP INCOMPLETE**
- Foundation Track: `PI-0..PI-25` merged as contracts, components, and scaffolds
- Active corrective track: `PIR-0..PIR-15`
- Current package: `PIR-12`
- Next action: implement Verification, recovery, checkpoint, and resume integration
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
- concrete Twin, Blueprint, and Convergence facades exist, but later consumer cutover remains incomplete;
- Verification adapter is not connected to real Atlas consumers;
- durability defects remain in Blueprint, event projection, and checkpoints;
- Verification, recovery, checkpoint, and resume production integration remain incomplete;
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
| PIR-6 | whole-project semantic graph | acceptance_complete |
| PIR-7 | CFG, data flow, state/event/resource graphs | acceptance_complete |
| PIR-8 | durable Blueprint planning and review | acceptance_complete |
| PIR-9 | Convergence correctness and evidence policy | acceptance_complete |
| PIR-10 | Planner and PlanPool production integration | acceptance_complete |
| PIR-11 | Proposal, Safe Apply, and refresh integration | acceptance_complete |
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

```text
Work package: PIR-6 — Whole-project semantic graph and parser-backed frontend analysis
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/analyzers/python.py — Python semantic analyzer now records source
  ranges, resolves receiver method calls from annotations and constructor assignments, and
  records Protocol/ABC-style implements edges.
- agent/project_twin/analyzers/registry.py — project-level linker resolves calls/imports
  through package re-export aliases after all files are analyzed.
- tests/test_project_intelligence_semantic_graph.py — labeled fixtures for re-export call
  resolution, receiver-type method resolution, Protocol implementation, source ranges, and
  incremental/full equivalence.
Executed commands and exact results:
- python -m py_compile agent/project_twin/analyzers/python.py
  agent/project_twin/analyzers/registry.py tests/test_project_intelligence_semantic_graph.py ->
  compile OK
- python -m pytest -q tests/test_project_intelligence_semantic_graph.py ->
  18 passed in 0.81s
- python -m pytest -q tests/test_project_intelligence_semantic_graph.py
  tests/test_project_intelligence_query_context.py tests/test_project_twin_static_graph.py
  tests/test_project_twin_verification_context.py tests/test_project_intelligence_recovery_baseline.py ->
  48 passed, 3 xfailed in 15.81s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 454 passed, 3 xfailed in 43.29s
Unavailable checks: no external LSP server was required; LSP-unavailable remains an explicit
  degraded fallback. The larger labeled precision/recall benchmark corpus remains tracked for
  final benchmark work.
Safety invariants checked: semantic analysis remains pure/read-only; unresolved dynamic calls
  remain bounded candidates with lower confidence; parser fallback is recorded as degraded,
  not silently equivalent; incremental invalidation keeps unchanged file facts.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: full CFG/data-flow/state/resource precision and frontend handler-scope
  behavior begin in PIR-7.
Next package: PIR-7 — real CFG, data-flow, state/event/recovery, and resource graphs.
Blocker: none.
```

```text
Work package: PIR-7 — Real CFG, data-flow, state/event/recovery, and resource graphs
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/behavioral_graph.py — production Digital Twin behavioral analyzer now
  emits per-callable CFG block nodes and branch/loop/exception/return edges; SSA-lite
  definition/use/resource flow facts; concrete file/database/API/process/UI resource
  identities; state transition nodes/edges; retry/backoff/rollback recovery facts; event
  producer facts; source ranges and bounded inferred confidence; JS event handlers now link
  only to API calls inside their reachable handler body instead of all APIs in the file.
- tests/test_project_twin_pir7_graphs.py — labeled PIR-7 corpus for branch/loop/exception,
  parameter-to-resource flow, cross-function argument propagation, state/recovery transitions,
  scoped UI handler-to-API paths, and a concrete DigitalTwinModuleImpl production connection.
- tests/test_project_intelligence_recovery_baseline.py — PIR-7 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_twin/behavioral_graph.py
  tests/test_project_twin_pir7_graphs.py -> compile OK
- python -m pytest -q tests/test_project_twin_pir7_graphs.py
  tests/test_project_twin_behavioral_graph.py tests/test_project_intelligence_behavioral_graph.py ->
  16 passed in 1.84s
- python -m pytest -q tests/test_project_twin_pir7_graphs.py
  tests/test_project_twin_behavioral_graph.py tests/test_project_intelligence_behavioral_graph.py
  tests/test_project_intelligence_recovery_baseline.py -> 24 passed, 3 xfailed in 14.49s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_twin_pir7_graphs.py
  tests/test_project_twin_behavioral_graph.py tests/test_project_intelligence_behavioral_graph.py
  tests/test_project_intelligence_semantic_graph.py tests/test_project_twin_source_refresh_lifecycle.py
  tests/test_project_twin_verification_context.py tests/test_project_intelligence_query_context.py
  tests/test_project_intelligence_recovery_baseline.py -> 61 passed, 3 xfailed in 20.21s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 457 passed, 3 xfailed in 44.00s
Unavailable checks: no live browser/runtime UI execution was required for this package; the
  package verifies parser/static graph facts and a concrete Twin facade refresh. PIR-13/PIR-14
  remain the real Greenfield E2E, platform, and rollout gates.
Safety invariants checked: behavioral facts remain inferred with confidence below 1.0; production
  Twin persists the facts behind the facade; frontend calls outside a handler are not promoted to
  reachable handler behavior; resource and state facts do not mutate PlanPool/Safe Apply authority.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: Blueprint target authority, Convergence gap policy, Planner/PlanPool integration,
  and final benchmark/retirement remain in PIR-8+.
Next package: PIR-8 — durable Blueprint planning, review, and critical-decision integration.
Blocker: none.
```

```text
Work package: PIR-8 — Durable Blueprint planning, review, and critical-decision integration
Status: acceptance_complete
Changed modules/files:
- agent/architecture_blueprint/contracts.py — BlueprintCreateRequest now carries structured
  requirement/actual context for target files, API/schema/config/dependency/runtime/NFR,
  preserve-behavior, command, approval, and critical-decision inputs.
- agent/architecture_blueprint/planner_adapter.py — new public-context planner adapter maps
  Requirement + Actual inputs into deterministic BlueprintSpec and adds an unresolved critical
  decision when an existing project requests full redesign without approval.
- agent/architecture_blueprint/generator.py — deterministic Blueprint generation now emits
  concrete file, API, schema, configuration, dependency, runtime, NFR, preserve-behavior,
  entrypoint, command, and test-contract target elements with planned bp:// identities and
  verification contracts.
- agent/architecture_blueprint/validator.py — validates command values, mandatory verification
  contracts, requirement verification coverage, unresolved decisions, planned-vs-Actual refs,
  dependency cycles, and full-project manifest/execution contracts.
- agent/architecture_blueprint/module.py and store.py — create uses the planner adapter,
  review persists durable diagnostics/decisions/topology/coverage artifacts, and activation
  revalidates the persisted revision before moving the active index.
- tests/test_architecture_blueprint_pir8.py and existing Blueprint tests — PIR-8 acceptance
  corpus for existing Change Blueprint, Greenfield full Blueprint, durable review/activation
  restart, critical-decision blocking, and target identity/verification contracts.
- tests/test_project_intelligence_recovery_baseline.py — PIR-8 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/architecture_blueprint/contracts.py
  agent/architecture_blueprint/generator.py agent/architecture_blueprint/planner_adapter.py
  agent/architecture_blueprint/validator.py agent/architecture_blueprint/module.py
  agent/architecture_blueprint/store.py tests/test_architecture_blueprint_pir8.py
  tests/test_project_intelligence_blueprint_lifecycle.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_architecture_blueprint_pir8.py
  tests/test_blueprint_durable_lifecycle.py tests/test_project_intelligence_blueprint_generation.py
  tests/test_project_intelligence_blueprint_lifecycle.py
  tests/test_project_intelligence_blueprint_mapping.py -> 26 passed in 2.24s
- python -m pytest -q tests/test_architecture_blueprint_pir8.py
  tests/test_blueprint_durable_lifecycle.py tests/test_project_intelligence_blueprint_generation.py
  tests/test_project_intelligence_blueprint_lifecycle.py tests/test_project_intelligence_blueprint_mapping.py
  tests/test_project_intelligence_recovery_baseline.py -> 34 passed, 3 xfailed in 15.21s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_architecture_blueprint_pir8.py
  tests/test_blueprint_durable_lifecycle.py tests/test_project_intelligence_blueprint_generation.py
  tests/test_project_intelligence_blueprint_lifecycle.py tests/test_project_intelligence_blueprint_mapping.py
  tests/test_project_intelligence_greenfield.py tests/test_project_intelligence_plan_compiler.py
  tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_recovery_baseline.py -> 50 passed, 3 xfailed in 16.18s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_architecture_blueprint_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 461 passed, 3 xfailed in 44.97s
Unavailable checks: no live Atlas UI critical-decision prompt was exercised in this package;
  unresolved Blueprint decisions surface through the existing Blueprint review/activation gate.
Safety invariants checked: target design uses bp:// planned identities; Actual refs remain only
  as expected materialization refs; existing-project full redesign requires explicit approval;
  review artifacts and active revision state persist; Blueprint does not mutate PlanPool, Twin,
  workspace, Proposal, Safe Apply, or Verification state.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: Convergence gap policy, Planner/PlanPool production integration, Proposal/
  Safe Apply refresh, recovery/resume, Greenfield E2E, platform rollout, benchmark, and legacy
  retirement remain in PIR-9+.
Next package: PIR-9 — Convergence correctness, evidence policy, and durable decisions.
Blocker: none.
```

```text
Work package: PIR-9 — Convergence correctness, evidence policy, and durable decisions
Status: acceptance_complete
Changed modules/files:
- agent/project_convergence/contracts.py — Convergence requests/reports now separate Actual
  Twin, source, requirement, mapping, and evidence revision identities; element results carry
  evidence policy, required evidence refs, and freshness state.
- agent/project_convergence/evaluator.py — evidence freshness compares verification source
  revision against Actual source revision, not Twin revision; mandatory gaps are retained until
  each element evidence policy passes; unavailable/observed/materialized evidence does not pass
  verified policies; typed dimension mismatches cover API/schema/config/dependency/behavior/
  state/recovery/resource/NFR-style contracts.
- agent/project_convergence/policy.py — completion candidate now requires every mandatory
  element result to be verified; the old any-verified shortcut is removed.
- agent/project_convergence/module.py and store.py — facade persists separated revision metadata
  in reports and exposes persisted decision history for restart proof.
- tests/test_project_convergence_pir9.py and existing Convergence/Completion tests — PIR-9
  corpus for source-vs-Twin revision correctness, mandatory evidence policies, unavailable
  evidence, typed dimensional gaps, persisted decisions, and no premature completion.
- tests/test_project_intelligence_recovery_baseline.py — PIR-9 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_convergence/contracts.py
  agent/project_convergence/evaluator.py agent/project_convergence/policy.py
  agent/project_convergence/module.py agent/project_convergence/store.py
  tests/test_project_convergence_pir9.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_convergence_pir9.py
  tests/test_project_intelligence_convergence_eval.py
  tests/test_project_intelligence_convergence_decision.py
  tests/test_convergence_module_durability.py tests/test_project_intelligence_completion.py ->
  31 passed in 2.43s
- python -m pytest -q tests/test_project_convergence_pir9.py
  tests/test_project_intelligence_convergence_eval.py
  tests/test_project_intelligence_convergence_decision.py
  tests/test_convergence_module_durability.py tests/test_project_intelligence_completion.py
  tests/test_project_intelligence_recovery_baseline.py -> 39 passed, 3 xfailed in 14.98s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_convergence_pir9.py
  tests/test_project_intelligence_convergence_eval.py
  tests/test_project_intelligence_convergence_decision.py
  tests/test_convergence_module_durability.py tests/test_project_intelligence_completion.py
  tests/test_project_intelligence_blueprint_generation.py tests/test_architecture_blueprint_pir8.py
  tests/test_project_intelligence_greenfield.py tests/test_project_intelligence_plan_compiler.py
  tests/test_project_intelligence_recovery_baseline.py -> 64 passed, 3 xfailed in 16.41s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_architecture_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_convergence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_convergence_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 467 passed, 3 xfailed in 45.87s
Unavailable checks: no live Planner/PlanPool production action was exercised in this package;
  PIR-10 owns authoritative PlanPool integration.
Safety invariants checked: source revision is not treated as Twin revision; unavailable evidence
  remains unavailable; materialized/observed does not satisfy verified evidence policies; Convergence
  returns bounded decisions only and does not mutate Blueprint, PlanPool, workspace, Proposal, Safe
  Apply, or Verification state.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: Planner/PlanPool production integration, Proposal/Safe Apply refresh, recovery/
  resume, Greenfield E2E, platform rollout, benchmark, and legacy retirement remain in PIR-10+.
Next package: PIR-10 — Planner and PlanPool production integration.
Blocker: none.
```

```text
Work package: PIR-10 — Planner and authoritative PlanPool production integration
Status: acceptance_complete
Changed modules/files:
- agent/project_intelligence/plan_compiler.py — Blueprint dependency cycles and missing
  dependencies now fail before PlanPool creation; pseudo Blueprint elements compile to
  non-file planning/verification items; planning envelope hashes and explicit
  Blueprint-element-to-PlanItem maps are persisted with revision refs.
- agent/project_intelligence/planpool_adapter.py — compiled Blueprint plans translate through
  the existing AtlasPlanPoolBuilder and AtlasPlanPoolStorage authority, preserving completed
  items and carrying Project Intelligence metadata onto pools and items.
- app/api/atlas_pipeline.py — production PlanPool creation invokes the registered Project
  Intelligence planning adapter in shadow/active modes, persists manifest/revision/readiness
  metadata on PlanPool state, and blocks active planning when PI context is stale/degraded.
- tests/test_project_intelligence_plan_compiler.py
- tests/test_project_intelligence_planpool_adapter.py
- tests/test_atlas_api_pipeline.py
- tests/test_project_intelligence_recovery_baseline.py — PIR0-C07 dependency-cycle lock now
  passes and PIR-10 status advanced; later package locks remain strict xfail.
Executed commands and exact results:
- python -m py_compile app/api/atlas_pipeline.py
  agent/project_intelligence/plan_compiler.py agent/project_intelligence/planpool_adapter.py
  tests/test_atlas_api_pipeline.py tests/test_project_intelligence_plan_compiler.py
  tests/test_project_intelligence_planpool_adapter.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_plan_compiler.py
  tests/test_project_intelligence_planpool_adapter.py tests/test_project_intelligence_planner_bridge.py
  tests/test_atlas_plan_pool_builder.py tests/test_atlas_plan_pool_storage.py
  tests/test_atlas_api_pipeline.py tests/test_project_intelligence_recovery_baseline.py ->
  91 passed, 2 xfailed in 24.21s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_architecture_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_convergence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_convergence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_atlas_plan_pool_*.py' | ForEach-Object { $_.FullName }) +
  @((Resolve-Path tests/test_atlas_api_pipeline.py).Path, (Resolve-Path tests/test_atlas_planner_bridge.py).Path);
  python -m pytest -q @files -> 566 passed, 2 xfailed in 57.30s
Unavailable checks: no live external Planner LLM success path or UI session was required; the
  production API path was exercised deterministically through PlanPool creation with a registered
  Project Intelligence service. PIR-11 owns Proposal/Safe Apply refresh and PIR-13 owns real
  Greenfield E2E.
Safety invariants checked: off/no-service PlanPool creation remains legacy-compatible; shadow
  mode is non-interfering; active stale/degraded PI context records a blocking PlanPool metadata
  reason rather than approving execution; PlanPool storage remains authoritative; Planner does
  not access private module stores; completed items remain completed during downstream replan.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: coordinator active context still depends on later real module-output work;
  Proposal, Safe Apply, refresh, recovery/resume, Greenfield E2E, platform rollout, benchmark,
  and legacy retirement remain in PIR-11+.
Next package: PIR-11 — Proposal, Safe Apply, and refresh integration.
Blocker: none.
```

```text
Work package: PIR-11 — Proposal, Safe Apply, refresh, and generation-context integration
Status: acceptance_complete
Changed modules/files:
- agent/atlas_patch_proposal_service.py — Proposal generation accepts an optional Project
  Intelligence coordinator, builds manifest-backed generation context at the canonical
  Proposal input boundary, persists generation manifest/base revision metadata in proposals,
  and blocks stale Actual/Twin revisions before model invocation.
- agent/atlas_safe_apply_execution_service.py — after canonical Safe Apply persistence,
  successful applies notify Project Intelligence through record_apply_result, persist Twin
  refresh and Convergence metadata on safe_apply, preserve canonical apply success on PI
  failure as degraded retry metadata, and avoid duplicate PI notification for the same run
  correlation.
- agent/project_intelligence/contracts.py and coordinator.py — post-apply results now carry
  Convergence report/decision metadata; active record_apply_result evaluates and persists
  a bounded Convergence report/decision through the public Convergence facade after Twin ingest.
- app/api/atlas_pipeline.py, app/api/atlas_autopilot_factory.py,
  app/api/atlas_multi_item_autopilot.py, app/api/atlas_autonomous_codegen.py — app-created
  Proposal/Safe Apply services now pass the registered Project Intelligence coordinator when
  available while no-service/off behavior remains unchanged.
- tests/test_project_intelligence_pir11_generation_apply.py — real Proposal and Safe Apply
  service coverage in a temporary workspace for generation metadata, stale no-call blocking,
  post-apply Twin refresh plus Convergence report/decision, and PI notification idempotence.
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/contracts.py
  agent/project_intelligence/coordinator.py agent/atlas_patch_proposal_service.py
  agent/atlas_safe_apply_execution_service.py app/api/atlas_pipeline.py
  app/api/atlas_autopilot_factory.py app/api/atlas_multi_item_autopilot.py
  app/api/atlas_autonomous_codegen.py
  tests/test_project_intelligence_pir11_generation_apply.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_pir11_generation_apply.py
  tests/test_project_intelligence_generator_bridge.py
  tests/test_atlas_patch_proposal_codegen_contract.py tests/test_atlas_patch_generation_incident.py
  tests/test_atlas_read_before_edit.py tests/test_atlas_safe_apply_metadata_persistence.py
  tests/test_atlas_api_pipeline.py tests/test_project_intelligence_recovery_baseline.py ->
  84 passed, 2 xfailed in 28.67s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
Unavailable checks: no live external UI session was required for this package. A broader legacy
  manual-flow batch was not used as proof because it contains unrelated stale tests that call
  /plan-pools without sync=1 and Windows default-encoding source reads.
Safety invariants checked: stale generation blocks before the LLM call; Proposal remains
  proposal-only and does not run Safe Apply; Safe Apply remains canonical mutation authority;
  Project Intelligence post-apply failures are recorded as degraded retry metadata and do not
  undo successful canonical apply; duplicate PI post-apply notification is suppressed by
  correlation ID; Convergence remains advisory and does not mutate PlanPool or workspace state.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: verification adapter production integration, recovery/resume, Greenfield E2E,
  platform rollout, benchmark, and legacy retirement remain.
Next package: PIR-12 — Verification, recovery, checkpoint, and resume integration.
Blocker: none.
```
