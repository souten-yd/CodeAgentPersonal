# Atlas Project Intelligence Recovery — Detailed Design

Status: canonical corrective implementation design.

This design repairs and completes the PI-0..PI-25 foundation. Existing helpers should be reused when correct, but production behavior must flow through concrete module facades and canonical Atlas boundaries.

## 1. Target package structure

```text
agent/
  project_twin/
    module.py                     # DigitalTwinModuleImpl
    source_adapter.py             # workspace-safe snapshots and revisions
    revision_store.py             # durable Twin revision metadata
    graph_store.py                # durable nodes/edges/facts by revision
    manifest_store.py             # durable Context Manifest records
    event_projection_store.py     # durable delivery trace and idempotency
    refresh_service.py            # full/incremental refresh transaction
    query_service.py              # public query dispatch
    source_materializer.py        # symbol-range revision-safe excerpts
    linker/                       # whole-project semantic link pass
    cfg/                          # real callable CFG
    dataflow/                     # def-use and bounded interprocedural flow
    resources/                    # resource canonicalization
    runtime/                      # observation store and reconciliation

  architecture_blueprint/
    module.py                     # repaired ArchitectureBlueprintModuleImpl
    store.py                      # durable revisions + lifecycle/reviews/active index
    planner_adapter.py            # Requirement/Actual -> BlueprintSpec
    reviewer.py                   # deterministic + optional model review
    validator.py                  # full contract validation

  project_convergence/
    module.py                     # ConvergenceModuleImpl
    comparator_registry.py        # typed dimension comparators
    mapping_store.py              # revision-pair mapping history
    store.py                      # report and decision persistence
    evaluator.py
    policy.py

  project_intelligence/
    production_factory.py         # only production composition root
    coordinator.py                # repaired real orchestration
    service_registry.py           # per-app/per-workspace lifecycle
    rollout_store.py              # durable phase state and evidence
    telemetry_store.py            # durable phase metrics
    adapters/
      atlas_planning.py
      atlas_generation.py
      atlas_apply.py
      atlas_verification.py
      atlas_continuation.py
      atlas_completion.py
    greenfield_state_machine.py
    benchmark_runner.py

app/api/
  atlas_pipeline.py               # adapters inserted at canonical boundaries
  atlas_project_intelligence.py   # read-only health/inspection/rollout diagnostics
  atlas_startup.py or app factory # service registration and close hooks
```

Names may be adapted to current repository conventions, but module ownership and public boundaries are mandatory.

## 2. Public facade conformance

All concrete modules must satisfy reusable conformance suites against the existing protocols.

### 2.1 Digital Twin facade

Required production methods:

```python
open_project(request) -> TwinProjectState
refresh(request) -> TwinRefreshResult
rebuild(request) -> TwinRefreshResult
ingest_event(event) -> TwinEventResult
ingest_runtime(request) -> RuntimeIngestResult
query(request) -> TwinQueryResult
build_context(request) -> TwinContextPackage
health(request) -> TwinHealthReport
```

### 2.2 Blueprint facade

Required production methods:

```python
create(request) -> BlueprintResult
revise(request) -> BlueprintResult
review(request) -> BlueprintReviewResult
activate(request) -> BlueprintRevision
get_active(request) -> BlueprintRevision | None
get_revision(request) -> BlueprintRevision
```

`get_active` must resolve the active Blueprint for `(project_id, workspace_id)` deterministically. If multiple Blueprint groups can exist, add an explicit active-project index rather than returning `None` or guessing.

### 2.3 Convergence facade

Required production methods:

```python
evaluate(request) -> ConvergenceReport
decide(request) -> ConvergenceDecision
get_latest(request) -> ConvergenceReport | None
```

The facade owns mapping/evaluation/persistence orchestration, but does not mutate PlanPool, Blueprint, or workspace.

## 3. Production composition root

### 3.1 Construction

Add a production-only factory:

```python
def build_production_project_intelligence(
    *,
    ca_data_dir: Path,
    rollout_config: RolloutConfig,
    source_adapter: ProjectSourceAdapter,
    command_authority: ExistingAtlasCommandAuthority,
    telemetry: TelemetryStore | None = None,
) -> ProjectIntelligenceCoordinator:
    ...
```

It must:

1. create project/workspace-safe persistent paths under `ca_data_dir`;
2. construct concrete Twin, Blueprint, and Convergence modules;
3. construct durable checkpoint, event projection, rollout, and telemetry stores;
4. construct the real Coordinator;
5. perform schema migration and integrity preflight;
6. fail closed if active mode is requested and required modules are disabled/corrupt;
7. expose close/flush hooks.

### 3.2 Application lifecycle

Register one service on application state, for example:

```text
request.app.state.atlas_project_intelligence
```

The application startup path performs construction once. Request handlers do not reconstruct stores per request. Shutdown closes SQLite connections and workers cleanly.

For multi-workspace operation, the service must key all state by `(project_id, workspace_id)` and never share mutable graph/session objects without that scope.

## 4. Durable persistence model

SQLite remains an internal adapter. Consumers never query tables directly.

### 4.1 Twin revision tables

Logical entities:

```text
twin_projects
  project_id, workspace_id, project_path_hash, active_revision_id, readiness

twin_revisions
  revision_id, project_id, workspace_id, source_revision_id,
  working_tree_hash, parent_revision_id, parser_manifest_hash,
  state, created_at, activated_at

twin_nodes
  revision_id, canonical_ref, kind, status, confidence,
  derivation, source_path, source_range_json, properties_json

twin_edges
  revision_id, edge_id, source_ref, target_ref, edge_kind,
  status, confidence, derivation, properties_json

twin_observations
  observation_id, project_id, workspace_id, source_revision_id,
  twin_revision_id, result, collector, payload_json, created_at

twin_reconciliations
  reconciliation_id, fact_ref, twin_revision_id, observation_ids_json,
  decision, status, payload_json

twin_context_manifests
  manifest_id, project_id, workspace_id, twin_revision_id,
  source_revision_id, phase, payload_json, created_at
```

Required uniqueness:

```text
(project_id, workspace_id)
(project_id, workspace_id, revision_id)
(revision_id, canonical_ref)
(revision_id, source_ref, target_ref, edge_kind, derivation)
(project_id, workspace_id, observation_id)
```

### 4.2 Event projection tables

```text
project_event_inbox
  event_id, idempotency_key, project_id, workspace_id,
  event_type, payload_json, state, attempts, last_error, created_at

delivery_nodes
  project_id, workspace_id, ref, kind, payload_json

delivery_edges
  project_id, workspace_id, source_ref, target_ref, edge_kind, payload_json
```

Event payload or a durable canonical lookup reference must be retained. A retry job containing only event ID/type is insufficient.

### 4.3 Blueprint lifecycle tables

Persist, not merely cache:

```text
blueprint_revisions
blueprint_reviews
blueprint_decisions
blueprint_status_history
blueprint_active_index
```

Status transitions and active-pointer updates must occur in a transaction with optimistic revision checks.

### 4.4 Convergence tables

```text
convergence_mappings
convergence_reports
convergence_element_results
convergence_decisions
completion_reports
```

Every report records separately:

```text
blueprint_revision_id
actual_twin_revision_id
actual_source_revision_id
verification_evidence_revision or observation IDs
mapping_revision_id
```

Never compare a source revision directly to a Twin revision.

### 4.5 Durable operational state

```text
pi_checkpoints
pi_greenfield_sessions
pi_rollout_state
pi_telemetry_events
pi_consumer_registry_snapshots
pi_benchmark_runs
```

Default production constructors must not use `:memory:`.

## 5. Digital Twin concrete implementation

### 5.1 Source adapter

`ProjectSourceAdapter.snapshot(project)` returns:

```text
project_id
workspace_id
safe_root
source_revision_id        # Git commit/base + dirty-tree identity
working_tree_hash
files: metadata and optional content handles
changed_paths since prior snapshot
ignored/excluded paths
```

Requirements:

- resolve and validate workspace root;
- reject path traversal and unsafe symlink escape;
- honor repository ignores plus configured exclusions;
- bound file count/size and report truncation/degradation;
- hash content deterministically;
- treat dirty working tree as a distinct source revision.

### 5.2 Refresh transaction

Full/incremental refresh sequence:

```text
acquire per-project/workspace refresh lease
-> snapshot source
-> select changed/invalidated files
-> parse file-local facts
-> run whole-project linker
-> build/update semantic graph
-> build CFG/data-flow/state/resource graphs
-> reconcile retained runtime observations against source revision
-> validate graph invariants
-> write immutable revision and facts in one transaction
-> activate revision
-> persist health/diagnostics
-> release lease
```

On failure, retain the prior active revision and mark readiness degraded/stale. Never partially activate a revision.

### 5.3 Whole-project semantic linker

The current file-local analyzers become extraction frontends. Add a second pass that:

- resolves project packages/modules from configured roots;
- validates imported modules and symbols exist;
- resolves aliases and re-exports transitively with cycle guards;
- builds class/type tables;
- resolves inheritance and overrides across modules;
- models Protocol/ABC implementation candidates;
- infers receiver targets from simple assignments, constructor calls, annotations, and parameters;
- emits exact resolved calls where proven and bounded candidate sets otherwise;
- records unresolved reasons explicitly.

No unknown dynamic call may be promoted to resolved.

### 5.4 Parser-backed JS/TS/Vue

Replace regex-only final behavior with a parser adapter behind the analyzer registry. Preferred options are tree-sitter or a TypeScript compiler/LSP adapter, selected according to dependency and platform constraints.

Required facts:

- imports/exports/re-exports;
- functions/classes/interfaces/types;
- Vue component, props, emits, template handlers, composables;
- router/API client references;
- DOM/render dependencies;
- source ranges.

If the parser is unavailable, retain heuristic fallback with degraded capability and never report parity.

### 5.5 Control-flow graph

Each callable receives:

```text
entry block
basic blocks
normal edges
conditional true/false edges
loop back edges
return edges
raise/exception edges
finally edges
exit block
```

Stable block IDs derive from callable ref and source range, not sequence order alone.

### 5.6 Data-flow graph

Implement SSA-lite/def-use facts for:

- parameters;
- assignments and reads;
- attributes when receiver identity is resolvable;
- call arguments and return values;
- condition predicates;
- route inputs and response outputs;
- schema/model construction;
- resource sinks.

Bounded interprocedural propagation follows resolved calls and stops at configured depth/fact budgets. Candidate calls create uncertain alternatives, never verified flow.

### 5.7 State/event/recovery graph

Represent explicit nodes and transitions for:

- enum/literal/status states;
- reducer transitions;
- assignments to known state fields;
- event producers and consumers;
- retries, attempt counters, backoff, timeout;
- rollback/compensation;
- failure and recovery branches.

Differentiate declared, inferred, and runtime-observed transitions.

### 5.8 Resource identities

Canonical forms:

```text
file://relative/path
filepattern://pattern
route://METHOD /path
schema://module#name
dbtable://database/table
sql://file#range
network://METHOD host/path
process://command-signature
dependency://ecosystem/name
config://file#key
ui://file#component-or-selector
```

Secrets, authorization headers, full environment values, and unrestricted absolute paths must be redacted.

### 5.9 Query/context

`build_context` must combine:

- target refs and source ranges;
- semantic/behavior/resource neighborhood;
- requirements and preserve behavior;
- active Blueprint contracts;
- latest Convergence gaps;
- delivery trace;
- runtime evidence;
- selected tests;
- incidents, Memory, Skills, and Nexus evidence through adapters.

Ranking must use objective match, phase, graph distance, confidence, evidence status, freshness, risk, and prior outcomes. The manifest records every included/excluded ref and reason.

Source excerpts must use symbol/source ranges and validate the source revision immediately before materialization.

## 6. Blueprint repaired implementation

### 6.1 Creation pipeline

```text
Requirement package + project mode + Actual context
-> BlueprintPlannerAdapter
-> structured BlueprintSpec
-> deterministic generator
-> deterministic validator
-> optional model reviewer
-> critical-decision extraction
-> durable proposed revision + review artifact
-> approval/activation through existing authority
```

### 6.2 Blueprint target model

Expand first-class element/contract support for:

```text
product/component/package/directory/file
function/class/interface/type
API route/request/response/error
schema/data model/database table/migration
configuration/dependency
entrypoint/build/start/test command
runtime scenario
state/event/recovery contract
NFR/performance/security/compatibility/accessibility
preserve behavior
verification contract
```

### 6.3 Scope safety

- Greenfield -> full-project.
- Existing project defaults to change-set.
- Full-project redesign on an existing project requires explicit approved architecture scope, not file-count threshold alone.
- Repair scope is limited to failed/divergent contracts unless a Convergence decision authorizes downstream replan or Blueprint revision.

### 6.4 Validation

Validate:

- exact target manifest;
- no duplicate/unsafe paths;
- dependency DAG;
- every mandatory requirement covered;
- interfaces and schemas are concrete;
- execution commands are non-empty and compatible with command authority;
- runtime scenarios have evidence expectations;
- preserve behaviors and NFRs have verification contracts;
- no planned refs are represented as Actual;
- no unresolved critical decisions before activation.

## 7. Convergence concrete implementation

### 7.1 Module flow

```text
load active Blueprint revision
-> load immutable Actual Twin snapshot
-> load mapping candidates/history
-> select deterministic mappings
-> run typed comparators
-> attach fresh verification/runtime/delivery evidence
-> persist immutable report
-> run bounded decision policy
-> persist decision
```

### 7.2 Typed comparator registry

Required comparator dimensions:

```text
materialization
structure/dependency
interface/signature/type
API/schema/error contract
data/storage/migration
configuration/dependency version
behavior/control/data-flow
state/event/recovery
side effect/resource
entrypoint/build/start/test
runtime scenario
requirement/delivery trace
NFR evidence
```

A comparator returns typed mismatches, evidence refs, freshness state, confidence, and required next evidence.

### 7.3 Evidence policy

Each Blueprint element declares or derives an evidence policy, such as:

```text
materialization_only
static_contract
verified_test
runtime_observation
performance_measurement
manual_critical_decision
```

A mandatory element is satisfied only when its policy is met. `materialized` or `observed` is not automatically verified.

### 7.4 Completion policy

`ConvergenceModule.decide` must never independently infer final completion from `any verified`.

Flow:

```text
ConvergenceReport
-> CompletionEvaluator(all mandatory requirements/elements/evidence)
-> if complete: COMPLETE
-> else bounded repair/replan/revise/continue/decision/halt
```

Blueprint element IDs and PlanItem IDs are mapped explicitly through PlanPool metadata; never assume equality.

## 8. Coordinator repaired behavior

### 8.1 `prepare_project`

- resolve identity and mode;
- open Twin;
- refresh/rebuild according to readiness and rollout phase;
- load/create Blueprint state as applicable;
- return actual readiness, revisions, and diagnostics.

### 8.2 `prepare_planning_context`

- off: return legacy package only;
- shadow: build real package, persist comparison artifact, return legacy input;
- active: require healthy concrete Twin; load active Blueprint/latest Convergence; build real context; return populated PlanningContextPackage.

Do not call and discard module output.

### 8.3 `prepare_generation_context`

- validate Actual/source/Blueprint/Convergence revisions;
- build target-specific source material and contracts;
- return populated GenerationContextPackage;
- block with typed stale/refresh result when preconditions fail.

### 8.4 `record_apply_result`

After canonical Safe Apply is persisted:

- accept only successful typed apply results;
- persist canonical event to durable inbox/outbox path;
- refresh Actual Twin for changed paths;
- evaluate incremental Convergence;
- return new revision/report and next-decision request.

Projection/refresh failure must not undo Safe Apply; it creates degraded state and retry work.

### 8.5 `record_verification_result`

- normalize real canonical verification artifacts;
- ingest observations into Twin;
- reconcile against the exact source revision;
- evaluate Convergence;
- evaluate Completion;
- persist checkpoint and decision;
- return bounded next action.

### 8.6 `evaluate_progress`

Load persisted current Blueprint, Twin, Convergence, delivery trace, and Completion report. Return truthful state; do not always return false and do not fabricate complete.

## 9. Atlas production integration points

### 9.1 Plan creation

In `app/api/atlas_pipeline.py`, before constructing the existing planner request:

1. obtain Project Intelligence service from app state;
2. prepare project;
3. build planning context via adapter;
4. layer or shadow according to rollout;
5. persist manifest/revision IDs on PlanPool metadata after authoritative creation.

The legacy planner remains the execution engine until cutover; Project Intelligence augments its input and later may provide deterministic compiled items.

### 9.2 Plan Compiler to PlanPool

Add an adapter that translates `CompiledPlan` into the existing `AtlasPlanPoolBuilder` input or an explicit PlanPool creation command. The existing storage service remains authoritative.

Must preserve:

- stable existing completed item IDs and statuses;
- dependencies;
- requirement IDs;
- target files/refs;
- verification contracts;
- Blueprint/Twin/Convergence/manifest revision metadata.

### 9.3 Proposal generation

At `AtlasPatchProposalService.build_proposal_input` or the nearest canonical input boundary:

- request GenerationContextPackage;
- block stale revisions;
- include Actual source, Blueprint contracts, gaps, preserve behavior, tests, and uncertainty;
- persist context manifest/base revision in Proposal metadata;
- revalidate source revision immediately before model invocation.

### 9.4 Safe Apply

After Safe Apply canonical persistence succeeds, emit the typed apply event. Do not place Twin writes inside the Safe Apply transaction.

### 9.5 Verification

After canonical verification persists, normalize its actual artifacts and call `record_verification_result`. Project Intelligence may gate final completion but does not change raw verification truth.

### 9.6 Continuation and recovery

Map Convergence decisions to existing services:

```text
continue -> existing continuation
repair_current_item -> self-correction with current item scope
replan_downstream -> existing replanning with explicit affected PlanItems
revise_blueprint -> Blueprint revision workflow
request_critical_decision -> critical-decision gate
halt_unsafe -> blocked safety state
complete -> final rollup candidate
```

No direct execution from Convergence.

## 10. Greenfield state machine

Durable states:

```text
NEW
PROJECT_PREPARED
BLUEPRINT_PROPOSED
WAITING_BLUEPRINT_DECISION
BLUEPRINT_ACTIVE
PLAN_COMPILED
SLICE_READY
PROPOSAL_READY
APPLY_COMPLETED
TWIN_REFRESHED
VERIFICATION_COMPLETED
CONVERGENCE_EVALUATED
REPAIR_REQUIRED
REPLAN_REQUIRED
NEXT_SLICE
COMPLETION_CANDIDATE
COMPLETED
BLOCKED
FAILED_RETRYABLE
```

Every transition records:

```text
session_id
project/workspace
requirement revision
Blueprint revision
Twin/source revision
PlanPool/item/proposal/apply/verification refs
Convergence report/decision
idempotency key
```

The state machine accepts typed canonical outcomes, not caller-provided Booleans such as `applied=True`.

## 11. Real runtime adapters

Runtime profile detection proposes commands but must validate against project manifests:

- Python: `pyproject.toml`, setup metadata, executable modules;
- JS/Vue: `package.json` scripts;
- HTML: static server/browser harness rather than platform-specific `open`;
- FastAPI: importable app plus readiness HTTP probe;
- persistence: real write/restart/read scenario;
- frontend/backend: backend health plus browser/API interaction.

Command execution uses the existing Atlas command authority and sandbox. Start success requires readiness evidence, not merely return code zero.

## 12. Consumer migration and rollout

### 12.1 Real consumer registry

Generate from source plus runtime telemetry:

```text
consumer name
capability
legacy entrypoint
facade entrypoint
current mode
call count
shadow parity status
rollback status
owner/tests
```

### 12.2 Cutover order

```text
read-only inspection
planning context
generation context
impact/test recommendation
post-apply refresh
verification ingest
repair/replan decisions
final completion
Greenfield orchestration
```

Each phase requires:

- production wiring tests;
- shadow artifacts from real tasks;
- no critical mismatch or documented superiority;
- rollback drill;
- regression budget pass.

### 12.3 Durable rollout controller

Persist rollout state and transition evidence. On threshold violation, automatically return the affected phase to its prior mode without deleting new artifacts.

## 13. Benchmark runner

`benchmark_runner.py` must run both systems from the normal Atlas entrypoint and collect artifacts.

Minimum run record:

```text
run_id
arm
constraints hash
repo seed/revision
requirement
model settings
tool authority
start/end time
token usage
PlanPool/Proposal/apply/verification refs
completion and false-success state
human interventions
retries/repairs
cost
platform
```

Metrics are computed from run artifacts, not supplied by the test.

## 14. Security and failure behavior

- Production active mode with disabled modules is an error.
- Corrupt stores retain prior good revision and block active promotion.
- Event projection is at-least-once and idempotent.
- Refresh jobs use leases and recover running jobs after restart.
- Source revisions are checked before planning/generation/apply/resume.
- Sensitive source/runtime fields are redacted in telemetry/export.
- Unavailable collectors remain unavailable.
- No module may push, merge, self-apply, or bypass approval.

## 15. Initial file-level implementation map

PIR-0 and PIR-1 begin with:

```text
agent/project_twin/module.py
agent/project_twin/source_adapter.py
agent/project_twin/revision_store.py
agent/project_twin/graph_store.py
agent/project_twin/event_projection_store.py
agent/project_convergence/module.py
agent/project_convergence/mapping_store.py
agent/project_intelligence/production_factory.py
agent/project_intelligence/service_registry.py
agent/project_intelligence/coordinator.py
agent/architecture_blueprint/module.py
agent/architecture_blueprint/store.py
app/api/atlas_pipeline.py
app/api/atlas_project_intelligence.py
tests/test_project_intelligence_recovery_baseline.py
tests/test_project_intelligence_production_composition.py
```

Do not start with deep graph rewrites before the concrete durable facade and production composition paths exist.

## 16. Implementation completeness rule

For every PIR package, the status record must distinguish:

```text
contracts implemented
component tests passed
production path connected
real acceptance evidence captured
cross-platform evidence captured
remaining limitations
```

A package may be `component_complete` while still `production_pending`; it must not be labeled simply `Completed` until its package acceptance level passes.
