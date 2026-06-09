# Atlas Project Intelligence — Detailed Design

Status: canonical implementation design.

This document converts the master goal, architecture, and contracts into concrete implementation boundaries, internal components, persistence structures, event mappings, sequences, failure behavior, and file-level integration points.

## 1. Design principles

1. Public isolation is by module facade, not by every helper function.
2. Each module owns its internal services and persistence adapters.
3. Canonical Atlas systems remain authoritative.
4. Planned and actual facts use separate namespaces and storage.
5. Every derived fact carries provenance, revision, confidence, and validity.
6. Inference is not verification.
7. All cross-module payloads are immutable public DTOs.
8. Production cutover is off -> shadow -> phased active.
9. Existing behavior is adapted before it is replaced.
10. A successful canonical operation is never rolled back because an advisory projection failed.

## 2. Module composition

### 2.1 Digital Twin Module

Recommended public class:

```python
class DigitalTwinService(DigitalTwinModule):
    def __init__(
        self,
        *,
        store: TwinStoreAdapter,
        source: ProjectSourceAdapter,
        analyzers: AnalyzerRegistry,
        runtime_adapters: RuntimeAdapterRegistry,
        event_projectors: EventProjectorRegistry,
        context_builder: TwinContextBuilder,
        job_store: ProjectionJobStore,
    ) -> None: ...
```

Recommended internal services:

```text
TwinLifecycleCoordinator
ProjectIdentityResolver
SourceSnapshotService
AnalyzerRegistry
GraphProjectionService
GraphInvalidationService
GraphQueryService
ImpactAnalysisService
RuntimeIngestionService
ReconciliationService
TwinContextBuilder
SourceMaterializer
ProjectionJobService
```

Only `DigitalTwinService` is used outside the module except explicitly versioned DTOs.

### 2.2 Architecture Blueprint Module

Recommended public class:

```python
class ArchitectureBlueprintService(ArchitectureBlueprintModule):
    def __init__(
        self,
        *,
        store: BlueprintStoreAdapter,
        generator: BlueprintGenerator,
        reviewer: BlueprintReviewer,
        validator: BlueprintValidator,
    ) -> None: ...
```

Internal services:

```text
BlueprintGenerator
ArchitectureOptionEvaluator
StackDecisionService
BlueprintValidator
BlueprintReviewer
BlueprintRevisionService
BlueprintDiffService
```

### 2.3 Convergence Module

Recommended public class:

```python
class ProjectConvergenceService(ConvergenceModule):
    def __init__(
        self,
        *,
        store: ConvergenceStoreAdapter,
        matcher: BlueprintActualMatcher,
        evaluator: ConvergenceEvaluator,
        policy: ConvergenceDecisionPolicy,
    ) -> None: ...
```

Internal services:

```text
BlueprintActualMatcher
StructuralConvergenceEvaluator
InterfaceConvergenceEvaluator
BehaviorConvergenceEvaluator
DataConvergenceEvaluator
ConfigurationConvergenceEvaluator
VerificationConvergenceEvaluator
DeliveryTraceConvergenceEvaluator
ConvergenceDecisionPolicy
IncrementalConvergencePlanner
```

### 2.4 Project Intelligence Module

Recommended public class:

```python
class AtlasProjectIntelligenceService(ProjectIntelligenceModule):
    def __init__(
        self,
        *,
        twin: DigitalTwinModule,
        blueprint: ArchitectureBlueprintModule,
        convergence: ConvergenceModule,
        rollout: ProjectIntelligenceRollout,
        telemetry: ProjectIntelligenceTelemetry,
    ) -> None: ...
```

Internal responsibilities:

- project preparation;
- project mode selection;
- Blueprint requirement decision;
- planning/generation package assembly;
- post-apply and post-verification orchestration;
- rollout and shadow comparison;
- checkpoint/progress summary.

It does not generate patches, execute tests, or mutate PlanPool.

## 3. Persistence design

A single SQLite file may host separate module tables, but table ownership and adapters remain isolated. Separate files may be used later without public-contract change.

### 3.1 Existing Twin tables

Existing PDT Core v1 tables remain readable. Migration adds workspace scoping and capability/version metadata through additive columns or v2 tables as safer.

Required logical entities:

```text
twin_projects
twin_revisions
twin_nodes
twin_edges
twin_evidence
twin_observations
twin_delta_log
twin_projection_jobs
twin_context_manifests
```

Required keys/indexes:

```text
(project_id, workspace_id)
(project_id, workspace_id, revision_id)
(project_id, workspace_id, canonical_ref, valid_to)
(project_id, workspace_id, source_node_id)
(project_id, workspace_id, target_node_id)
(project_id, workspace_id, idempotency_key) UNIQUE
```

### 3.2 Blueprint tables

```sql
CREATE TABLE blueprint_projects (
    project_id TEXT NOT NULL,
    blueprint_id TEXT NOT NULL,
    active_revision_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, blueprint_id)
);

CREATE TABLE blueprint_revisions (
    revision_id TEXT PRIMARY KEY,
    blueprint_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    parent_revision_id TEXT,
    scope TEXT NOT NULL,
    project_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    source_twin_revision_id TEXT,
    contract_version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    activated_at TEXT
);

CREATE TABLE blueprint_elements (
    revision_id TEXT NOT NULL,
    element_id TEXT NOT NULL,
    canonical_ref TEXT NOT NULL,
    element_type TEXT NOT NULL,
    mandatory INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (revision_id, element_id)
);

CREATE TABLE blueprint_relations (
    revision_id TEXT NOT NULL,
    relation_id TEXT NOT NULL,
    source_element_id TEXT NOT NULL,
    target_element_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (revision_id, relation_id)
);

CREATE TABLE blueprint_reviews (
    review_id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL,
    result TEXT NOT NULL,
    diagnostics_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

An activated Blueprint revision is immutable. Activation updates only the active pointer and activation metadata in one transaction.

### 3.3 Convergence tables

```sql
CREATE TABLE convergence_reports (
    report_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    blueprint_revision_id TEXT NOT NULL,
    actual_twin_revision_id TEXT NOT NULL,
    requirement_revision_id TEXT,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE convergence_element_results (
    report_id TEXT NOT NULL,
    blueprint_element_id TEXT NOT NULL,
    state TEXT NOT NULL,
    confidence REAL NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (report_id, blueprint_element_id)
);

CREATE TABLE convergence_decisions (
    decision_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

Reports are immutable. A newer report references newer input revisions rather than replacing an older report.

### 3.4 Job and outbox tables

```sql
CREATE TABLE project_intelligence_outbox (
    event_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE project_intelligence_jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    state TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    expected_revision_id TEXT,
    payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

States:

```text
queued, running, succeeded, failed_retryable, failed_terminal, cancelled, superseded
```

Jobs for the same project/workspace may be coalesced when their changed-path sets can be safely unioned and no strict revision precondition would be lost.

## 4. Canonical event projection design

### 4.1 Producer rule

Canonical owners emit an event only after their canonical write succeeds. The event is saved to an outbox/journal boundary that survives restart.

### 4.2 Projection mapping

| Event | Main projection |
|---|---|
| project.opened | project/workspace identity and lifecycle trigger |
| workspace.changed | static/semantic/behavior incremental refresh |
| conversation.message.completed | conversation/message nodes |
| requirement.confirmed/revised | requirement/constraint nodes and source links |
| plan.created/revised | plan and PlanItem nodes with requirement/Blueprint refs |
| plan_item.started/completed/failed | execution state history and changed refs |
| proposal.generated/approved/rejected | proposal nodes and status history |
| safe_apply.completed | run, applied files, source revision, refresh trigger |
| verification.started/completed | verification/test/evidence relations |
| runtime_observation.recorded | runtime nodes/edges and reconciliation |
| memory.* | learning-domain references only |
| skill.* | skill registration/activation/outcome references |
| nexus.evidence.added | external-evidence reference and support/contradiction edges |

### 4.3 Failure behavior

```text
canonical write succeeds
-> event saved
-> projection attempt fails
-> canonical result remains successful
-> Twin readiness becomes degraded if material
-> retryable job/outbox state recorded
-> consumer receives diagnostics and current usable revision
```

No projector may call back into the canonical service to rewrite status.

## 5. Digital Twin graph implementation details

### 5.1 Common graph fact

Every node/edge stores:

```text
project_id
workspace_id
canonical_ref
fact kind / relation kind
source kind and source ref
source revision
parser/analyzer version
derivation
confidence
status
valid_from / valid_to
evidence refs
properties
```

Current statuses remain distinct from historical statuses. Inferred facts cannot be presented as verified.

### 5.2 Analyzer execution

```text
SourceSnapshot
-> changed path classification
-> AnalyzerRegistry selects adapters
-> adapters return GraphDelta + diagnostics + capabilities
-> GraphProjectionService validates identities
-> InvalidationService retires superseded facts
-> store applies one atomic revision
```

Adapters do not write to the store directly.

### 5.3 Python semantic analysis

Minimum implementation sequence:

1. module/package resolution;
2. symbol table per module;
3. import alias and re-export resolution;
4. class hierarchy and method override;
5. Protocol/interface implementation;
6. call-site extraction;
7. deterministic target resolution;
8. candidate target set for dynamic dispatch;
9. framework extensions for FastAPI/Pydantic/dependency injection.

LSP supplements AST facts. It does not replace deterministic local analysis and its unavailable state is reported.

### 5.4 JavaScript/TypeScript/Vue analysis

Minimum sequence:

1. module import/export resolution;
2. function/class/component symbols;
3. Vue SFC script/template/style sections;
4. props/emits;
5. event handlers and state mutations;
6. router/API client references;
7. DOM/assets/CSS relations;
8. render dependencies.

A parser library may be introduced behind the analyzer adapter after dependency/safety review. Regex-only parsing is not the final implementation.

### 5.5 Control-flow graph

Each callable has stable basic-block refs derived from source location and callable identity. Blocks include statements and outgoing conditions. Exception edges are explicit. Unsupported dynamic constructs retain a conservative unknown edge and diagnostic rather than a fabricated path.

### 5.6 Data-flow graph

Initial supported facts:

- parameter definitions;
- assignments and reads;
- attribute writes/reads when resolvable;
- call arguments and return values;
- simple transformations;
- route input/output schema links;
- database/file/network sinks.

Interprocedural propagation is bounded by call depth and analysis budget. Unknown aliasing is recorded as uncertainty.

### 5.7 State/event/recovery graph

State extraction sources:

- explicit Enum/Literal state models;
- reducer functions;
- status-field assignments;
- workflow transition tables;
- event handlers and journal events;
- retry/timeout/rollback code paths.

Edges distinguish declared transitions, inferred transitions, and observed transitions.

### 5.8 Resource identity

Resource canonical refs:

```text
dbtable://database/table
sqlquery://file#callsite
filepath://relative/or/sanitized-target
network://METHOD host/path
process://command-signature
ui://file#selector-or-component
```

Secrets, credentials, raw sensitive payloads, and unrestricted absolute paths are never stored in graph properties.

## 6. Context construction design

### 6.1 Candidate sources

```text
exact target refs
1-3 hop graph neighborhood
impact result
requirement and Blueprint relations
Convergence gaps
recommended tests
runtime observations
incidents/memory/skills/Nexus
```

### 6.2 Ranking factors

A deterministic score uses target match, graph distance, phase relevance, objective relevance, confidence, evidence quality, freshness, and historical outcome. Stale and contradicted facts receive penalties.

### 6.3 Required order in generation context

```text
requirements and constraints
Blueprint contracts
preserve behavior
current target source
required interfaces
related symbols
behavior/state paths
side effects/resources
tests and runtime evidence
Convergence gaps
incidents/memory/skills/Nexus
uncertainty
```

### 6.4 Source material

The Twin stores identities and relations, not duplicate whole files. `SourceMaterializer` reads current source under workspace path safety, validates source revision, applies size limits, and records excerpt hashes in the context manifest.

## 7. Blueprint detailed behavior

### 7.1 Creation modes

#### Full project

Used for empty projects or explicit whole-system redesign.

#### Change set

Used for normal existing-project changes. It contains affected target design plus preserve behavior and constraints, not a regenerated full architecture.

#### Repair

Used only when a repair changes target contract. Normal implementation bugs do not require a repair Blueprint.

### 7.2 Required Greenfield elements

At minimum:

- product and components;
- selected stack and architecture decisions;
- exact directories/files;
- dependencies and manifests;
- public interfaces;
- API and schemas;
- data/persistence models;
- entrypoints;
- build/start/test commands;
- behavior/error/recovery;
- runtime scenarios;
- nonfunctional requirements;
- requirement and verification mapping.

### 7.3 Validation result

Validation produces typed diagnostics with severity:

```text
info, warning, revision_required, critical_decision_required, unsafe
```

A Blueprint with revision-required, critical-decision, or unsafe diagnostics cannot become active.

## 8. Convergence detailed behavior

### 8.1 Mapping

Matcher produces candidates and selected deterministic matches. Candidate-only mappings remain uncertain.

### 8.2 Evaluation order

For each mandatory element:

1. determine existence/materialization;
2. compare interface/schema/configuration contract;
3. compare structural and dependency relations;
4. compare inferred behavior;
5. locate matching runtime evidence;
6. verify evidence source revision and freshness;
7. evaluate requirement/delivery trace;
8. classify state and gaps.

### 8.3 Gap types

```text
missing_file
missing_symbol
unresolved_import
missing_dependency
interface_mismatch
api_schema_mismatch
behavior_missing
behavior_divergent
state_transition_missing
side_effect_missing
unexpected_side_effect
entrypoint_failure
build_failure
startup_failure
test_missing
test_failed
runtime_unavailable
stale_evidence
requirement_trace_missing
blueprint_invalid
unsafe_operation_required
```

### 8.4 Decision rules

- local implementation defect -> `repair_current_item`;
- interface change affecting unexecuted dependents -> `replan_downstream`;
- target design invalid or environment-incompatible -> `revise_blueprint`;
- unresolved policy/user choice -> `request_critical_decision`;
- safety boundary required -> `halt_unsafe`;
- current item satisfied and work remains -> `continue`;
- all mandatory gates satisfied -> `complete`.

## 9. Planner and Plan Compiler design

### 9.1 Architecture Planner

Creates or revises Blueprint only when project mode or gap decision requires it.

### 9.2 Delivery Planner

Receives PlanningContextPackage and proposes implementation strategy. Deterministic compiler performs:

- dependency topological sort;
- Blueprint element grouping;
- requirement assignment;
- target path normalization;
- PlanItem ID and dependency creation;
- completed-item preservation;
- verification contract propagation.

### 9.3 Repair Planner

Receives failed evidence, current Actual revision, active Blueprint contract, current Convergence gaps, and last successful checkpoint. It cannot broaden scope without a downstream replan or Blueprint revision decision.

## 10. Production integration points

### Planner

Integrate before `TaskPlanningRunner.run` advisory/context assembly in `AtlasPlannerBridge`. Preserve legacy context for off/shadow and store the context manifest in PlanPool metadata.

### Generator

Integrate in `AtlasPatchProposalService.build_proposal_input`. Preserve current target grounding and sibling-file manifest, then add Project Intelligence contracts and gaps. Validate Actual revision immediately before LLM generation.

### Safe Apply

After canonical Safe Apply result persists, emit `safe_apply.completed` with changed files and new source revision. Do not call private Twin store methods from executor.

### Verification

After canonical verification result persists, emit normalized verification/runtime events through adapter. Verification remains authoritative.

### Final rollup

Combine canonical requirement/verification result with Convergence mandatory gates. Off mode preserves legacy behavior.

## 11. Greenfield orchestration sequence

```text
prepare_project
-> mode = empty/greenfield_partial
-> create/review/activate Blueprint
-> compile first dependency slice
-> generate Proposal
-> Safe Apply
-> emit event and refresh Actual Twin
-> evaluate Convergence
-> continue or repair/replan/revise
-> build/test/start through existing execution authority
-> ingest runtime evidence
-> final Convergence and rollup
```

Each slice checkpoint stores all input revision IDs. Resume revalidates source revision before continuing.

## 12. Rollout and telemetry

Telemetry records only necessary metadata and summaries, not raw secrets or unrestricted source.

Required comparison fields:

```text
phase
legacy/new context tokens
legacy/new selected refs
latency
planner/generator result category
verification outcome
retry count
Convergence decision
human intervention
```

Active rollout is blocked when shadow shows material false negatives, stale facts, increased false success, or unacceptable latency without explicit waiver.

## 13. Failure and recovery matrix

| Failure | Required behavior |
|---|---|
| Twin store unavailable | degraded/off fallback according to rollout; no false readiness |
| parser failure | retain last valid revision, record stale/diagnostic |
| event projection failure | canonical result kept, retry job queued |
| stale Twin before generation | refresh or block generation |
| Blueprint validation failure | revision required; no activation |
| Convergence unavailable | no completion; legacy behavior only in allowed off/fallback mode |
| verification unavailable | incomplete/unavailable, not passed |
| restart during job | recover queued/running state idempotently |
| source changed externally | invalidate checkpoint and refresh/replan as needed |
| DB corruption | explicit corrupt state, backup/rebuild; no silent reset of durable Blueprint |

## 14. Security and privacy

- enforce workspace-relative safe source reads;
- do not store secrets or full environment values;
- redact sensitive command arguments and HTTP headers;
- preserve command allowlist and sandbox boundaries;
- graph analysis is read-only;
- runtime collectors are opt-in through existing verification authority;
- API inspection endpoints are read-only unless a future separately approved design adds mutation.

## 15. File-level first implementation map

PI-0 and PI-1 should begin with:

```text
AGENTS.md
docs/atlas_project_intelligence_*.md
agent/project_intelligence/__init__.py
agent/project_intelligence/contracts.py
agent/project_intelligence/facade.py
agent/project_twin/facade.py
agent/architecture_blueprint/__init__.py
agent/architecture_blueprint/contracts.py
agent/architecture_blueprint/facade.py
agent/project_convergence/__init__.py
agent/project_convergence/contracts.py
agent/project_convergence/facade.py
tests/test_project_intelligence_baseline.py
tests/test_project_intelligence_contracts.py
tests/test_project_intelligence_boundaries.py
```

Do not broadly move old code during PI-1. Facades and compatibility stubs are introduced first.

## 16. Definition of implementation completeness

A feature is not considered implemented because a class or table exists. It must have:

- production or approved shadow wiring;
- deterministic contract tests;
- module behavior tests;
- failure/recovery tests;
- real data path or real E2E evidence;
- current status entry;
- no unresolved authority or dependency violation.
