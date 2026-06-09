# Atlas Project Intelligence — Public Contracts

Status: canonical contract design.

The contracts in this document define module boundaries. Implementation may add private fields and helpers, but cross-module consumers must use versioned public models and facades.

## 1. Contract families

```text
atlas.project_intelligence.v1
atlas.digital_twin.v2
atlas.architecture_blueprint.v1
atlas.project_convergence.v1
```

The existing `atlas.project_twin.v1` contracts remain readable during migration. New facades adapt v1 data where possible; they do not rewrite old records in place.

Compatibility rules:

- additive optional fields are backward compatible;
- removing or renaming a required field requires a new major contract;
- enum additions require tolerant readers;
- persisted records always carry a contract version;
- migration failures must be explicit and rollback-safe;
- no consumer may infer success from an unknown enum value.

## 2. Common identity

```python
class ProjectIdentity(BaseModel):
    project_id: str
    workspace_id: str
    project_path: str
    repository_identity: str | None
    branch_or_worktree: str | None
    source_revision: str | None
    working_tree_hash: str
```

`project_id` identifies the logical project. `workspace_id` separates simultaneous worktrees or execution sandboxes. All persistence and query operations are scoped by both where relevant.

## 3. Digital Twin facade

```python
class DigitalTwinModule(Protocol):
    def open_project(self, request: OpenTwinRequest) -> TwinProjectState: ...
    def refresh(self, request: RefreshTwinRequest) -> TwinRefreshResult: ...
    def rebuild(self, request: RebuildTwinRequest) -> TwinRefreshResult: ...
    def ingest_event(self, event: ProjectEventEnvelope) -> TwinEventResult: ...
    def ingest_runtime(self, request: RuntimeIngestRequest) -> RuntimeIngestResult: ...
    def query(self, request: TwinQueryRequest) -> TwinQueryResult: ...
    def build_context(self, request: TwinContextRequest) -> TwinContextPackage: ...
    def health(self, request: TwinHealthRequest) -> TwinHealth: ...
```

### 3.1 Lifecycle models

```python
class TwinReadiness(str, Enum):
    ABSENT = "absent"
    BUILDING = "building"
    READY = "ready"
    STALE = "stale"
    DEGRADED = "degraded"
    CORRUPT = "corrupt"
    DISABLED = "disabled"

class OpenTwinRequest(BaseModel):
    project: ProjectIdentity
    requested_capabilities: set[str] = set()
    rollout_mode: str = "off"
    correlation_id: str

class TwinProjectState(BaseModel):
    project: ProjectIdentity
    readiness: TwinReadiness
    twin_revision_id: str | None
    parser_versions: dict[str, str]
    available_capabilities: set[str]
    stale_reasons: list[str]
    diagnostics: list[dict]
```

### 3.2 Refresh models

```python
class RefreshTwinRequest(BaseModel):
    project: ProjectIdentity
    changed_paths: list[str]
    trigger_type: str
    trigger_ref: str | None
    expected_revision_id: str | None
    correlation_id: str
    full_rebuild: bool = False

class TwinRefreshResult(BaseModel):
    project_id: str
    workspace_id: str
    previous_revision_id: str | None
    twin_revision_id: str | None
    readiness: TwinReadiness
    changed_node_count: int
    changed_edge_count: int
    invalidation_count: int
    affected_refs: list[str]
    diagnostics: list[dict]
```

### 3.3 Event envelope

```python
class ProjectEventEnvelope(BaseModel):
    contract_version: str
    event_id: str
    event_type: str
    project_id: str
    workspace_id: str
    source: str
    source_ref: str | None
    source_revision: str | None
    occurred_at: datetime
    idempotency_key: str
    correlation_id: str
    causation_event_id: str | None
    run_id: str | None
    plan_pool_id: str | None
    plan_item_id: str | None
    payload: dict[str, Any]
```

Required event catalog:

```text
project.opened
workspace.changed
conversation.message.completed
requirement.confirmed
requirement.revised
plan.created
plan.revised
plan_item.started
plan_item.completed
plan_item.failed
proposal.generated
proposal.approved
proposal.rejected
safe_apply.completed
verification.started
verification.completed
runtime_observation.recorded
memory.promoted
memory.superseded
skill.registered
skill.activated
skill.outcome.recorded
nexus.evidence.added
```

Event ingestion is at-least-once. Idempotency is mandatory.

### 3.4 Query models

```python
class TwinQueryKind(str, Enum):
    SNAPSHOT = "snapshot"
    SEARCH = "search"
    PATH = "path"
    IMPACT = "impact"
    TEST_SELECTION = "test_selection"
    DELIVERY_TRACE = "delivery_trace"
    SOURCE_CONTEXT = "source_context"

class TwinQueryRequest(BaseModel):
    project_id: str
    workspace_id: str
    revision_id: str | None
    kind: TwinQueryKind
    refs: list[str] = []
    text: str | None = None
    domains: list[str] = []
    statuses: list[str] = []
    max_depth: int = 5
    limit: int = 100
    options: dict[str, Any] = {}
```

The public result is a stable summary package, not a direct SQLite row or private graph object.

### 3.5 Context package

```python
class TwinContextRequest(BaseModel):
    project_id: str
    workspace_id: str
    objective: str
    phase: str
    target_refs: list[str]
    token_budget: int
    min_confidence: float = 0.25
    include_unverified: bool = True
    include_contradictions: bool = True

class TwinContextPackage(BaseModel):
    project_id: str
    workspace_id: str
    twin_revision_id: str | None
    phase: str
    requirements: list[ContextItem]
    symbols: list[ContextItem]
    interfaces: list[ContextItem]
    behavior_paths: list[ContextItem]
    state_and_events: list[ContextItem]
    side_effects: list[ContextItem]
    tests: list[ContextItem]
    runtime_evidence: list[ContextItem]
    incidents: list[ContextItem]
    memories: list[ContextItem]
    skills: list[ContextItem]
    nexus_evidence: list[ContextItem]
    preserve_behaviors: list[ContextItem]
    uncertainties: list[ContextItem]
    source_material: list[SourceExcerpt]
    manifest: ContextManifest
```

## 4. Architecture Blueprint facade

```python
class ArchitectureBlueprintModule(Protocol):
    def create(self, request: BlueprintCreateRequest) -> BlueprintResult: ...
    def revise(self, request: BlueprintRevisionRequest) -> BlueprintResult: ...
    def review(self, request: BlueprintReviewRequest) -> BlueprintReviewResult: ...
    def activate(self, request: BlueprintActivationRequest) -> BlueprintRevision: ...
    def get_active(self, request: BlueprintGetRequest) -> BlueprintRevision | None: ...
    def get_revision(self, request: BlueprintGetRevisionRequest) -> BlueprintRevision: ...
```

### 4.1 Blueprint revision

```python
class BlueprintRevision(BaseModel):
    contract_version: str
    blueprint_id: str
    revision_id: str
    project_id: str
    workspace_id: str | None
    parent_revision_id: str | None
    scope: Literal["full_project", "change_set", "repair"]
    source_requirement_ids: list[str]
    source_twin_revision_id: str | None
    project_mode: str
    status: str
    selected_architecture: ArchitectureDecision
    elements: list[BlueprintElement]
    relations: list[BlueprintRelation]
    constraints: list[str]
    assumptions: list[str]
    unresolved_decisions: list[BlueprintDecisionRequest]
    created_at: datetime
    activated_at: datetime | None
```

Blueprint revisions are immutable. Revision creates a child; it never edits an activated parent in place.

### 4.2 Blueprint element

```python
class BlueprintElement(BaseModel):
    element_id: str
    canonical_ref: str
    element_type: str
    name: str
    description: str
    mandatory: bool
    requirement_ids: list[str]
    depends_on_element_ids: list[str]
    expected_actual_refs: list[str]
    acceptance_criteria: list[str]
    verification_contract_ids: list[str]
    preserve_behaviors: list[str]
    properties: dict[str, Any]
```

Supported element types include product, component, package, directory, file, symbol, interface, API route, request/response schema, data model, table, configuration, environment variable, dependency, event, state, transition, behavior, side effect, error case, recovery behavior, test contract, runtime scenario, startup contract, deployment contract, and nonfunctional requirement.

### 4.3 Architecture decision

```python
class ArchitectureDecision(BaseModel):
    decision_id: str
    topic: str
    candidates: list[ArchitectureOption]
    selected_option_id: str
    selection_reasons: list[str]
    rejected_reasons: dict[str, list[str]]
    user_constraints: list[str]
    environment_constraints: list[str]
    dependency_risks: list[str]
    authority: Literal["user_decision", "policy_decision", "planner_recommendation"]
```

A model may produce `planner_recommendation`; it may not fabricate `user_decision`.

## 5. Convergence facade

```python
class ConvergenceModule(Protocol):
    def evaluate(self, request: ConvergenceRequest) -> ConvergenceReport: ...
    def decide(self, request: ConvergenceDecisionRequest) -> ConvergenceDecision: ...
    def get_latest(self, request: ConvergenceGetRequest) -> ConvergenceReport | None: ...
```

### 5.1 Evaluation request

```python
class ConvergenceRequest(BaseModel):
    project_id: str
    workspace_id: str
    blueprint_revision_id: str
    actual_twin_revision_id: str
    requirement_revision_id: str | None
    changed_refs: list[str] = []
    verification_refs: list[str] = []
    full_evaluation: bool = False
```

### 5.2 Element result

```python
class ElementConvergenceResult(BaseModel):
    blueprint_element_id: str
    state: Literal[
        "absent", "partial", "materialized", "observed", "verified",
        "divergent", "blocked", "stale"
    ]
    matched_actual_refs: list[str]
    missing_actual_refs: list[str]
    evidence_refs: list[str]
    mismatches: list[ConvergenceMismatch]
    confidence: float
```

### 5.3 Report and decision

```python
class ConvergenceReport(BaseModel):
    report_id: str
    project_id: str
    workspace_id: str
    blueprint_revision_id: str
    actual_twin_revision_id: str
    element_results: list[ElementConvergenceResult]
    mandatory_gaps: list[GapSummary]
    optional_gaps: list[GapSummary]
    stale_evidence: list[str]
    requirement_coverage: dict[str, Any]
    diagnostics: list[dict]
    generated_at: datetime

class ConvergenceDecision(BaseModel):
    action: Literal[
        "continue", "complete", "repair_current_item", "replan_downstream",
        "revise_blueprint", "request_critical_decision", "halt_unsafe"
    ]
    reason_codes: list[str]
    affected_blueprint_elements: list[str]
    affected_plan_items: list[str]
    mandatory_gaps: list[str]
```

Decision policy is deterministic where possible and independently testable. It does not execute the decision.

## 6. Project Intelligence facade

```python
class ProjectIntelligenceModule(Protocol):
    def prepare_project(self, request: PrepareProjectRequest) -> ProjectIntelligenceState: ...
    def prepare_planning_context(self, request: PlanningContextRequest) -> PlanningContextPackage: ...
    def prepare_generation_context(self, request: GenerationContextRequest) -> GenerationContextPackage: ...
    def record_apply_result(self, request: ApplyResultRequest) -> PostApplyIntelligenceResult: ...
    def record_verification_result(self, request: VerificationResultRequest) -> PostVerificationIntelligenceResult: ...
    def evaluate_progress(self, request: ProgressRequest) -> ProjectProgressResult: ...
```

### 6.1 Project mode

```python
class ProjectMode(str, Enum):
    EMPTY = "empty"
    GREENFIELD_PARTIAL = "greenfield_partial"
    EXISTING = "existing"
    GENERATED_UNVERIFIED = "generated_unverified"
    IMPORTED_UNKNOWN = "imported_unknown"
```

`.git`, `.gitignore`, `.gitkeep`, OS metadata, Atlas metadata, and empty documentation do not by themselves make a project existing.

### 6.2 Planning context package

```python
class PlanningContextPackage(BaseModel):
    project_state: ProjectStateSummary
    project_mode: ProjectMode
    actual_twin_revision_id: str | None
    blueprint_revision_id: str | None
    convergence_report_id: str | None
    requirements: list[RequirementSummary]
    current_architecture: ArchitectureSummary
    target_architecture: ArchitectureSummary | None
    impacted_areas: list[ImpactSummary]
    unresolved_gaps: list[GapSummary]
    relevant_tests: list[TestSummary]
    critical_decisions: list[DecisionSummary]
    uncertainties: list[UncertaintySummary]
    context_manifest: ContextManifest
```

### 6.3 Generation context package

```python
class GenerationContextPackage(BaseModel):
    project_id: str
    workspace_id: str
    plan_pool_id: str
    plan_item_id: str
    actual_twin_revision_id: str
    blueprint_revision_id: str | None
    convergence_report_id: str | None
    target_files: list[SourceFileContext]
    blueprint_contracts: list[BlueprintContractSummary]
    actual_symbols: list[SymbolSummary]
    required_interfaces: list[InterfaceSummary]
    behavior_paths: list[BehaviorPathSummary]
    preserve_behaviors: list[str]
    convergence_gaps: list[GapSummary]
    verification_requirements: list[VerificationRequirement]
    prohibited_divergences: list[str]
    context_manifest: ContextManifest
```

## 7. PlanPool extension contract

PlanPool additions are optional during shadow mode and required before active generation:

```text
blueprint_revision_id
actual_twin_revision_id
convergence_report_id
context_manifest_id
planning_envelope_hash
project_mode
```

PlanItem additions:

```text
blueprint_element_ids
expected_actual_refs
convergence_criteria
interface_contracts
behavior_contracts
required_evidence
replan_scope
```

Old PlanPool records remain readable with empty defaults.

## 8. Runtime observation contract

```python
class RuntimeObservationRecord(BaseModel):
    observation_id: str
    project_id: str
    workspace_id: str
    run_id: str | None
    collector: str
    collector_version: str
    observation_type: str
    subject_refs: list[str]
    source_revision: str | None
    timestamp: datetime
    result: Literal["passed", "failed", "observed", "unavailable"]
    summary: str
    evidence_refs: list[str]
    payload_ref: str | None
```

`unavailable` cannot be converted to `passed` by adapters, reconciliation, convergence, UI, or final rollup.

## 9. Context manifest

Every planning, generation, verification, and repair context package stores:

```python
class ContextManifest(BaseModel):
    manifest_id: str
    project_id: str
    workspace_id: str
    phase: str
    actual_twin_revision_id: str | None
    blueprint_revision_id: str | None
    convergence_report_id: str | None
    included_refs: list[str]
    excluded_refs: list[str]
    evidence_refs: list[str]
    uncertainty_refs: list[str]
    source_revisions: dict[str, str]
    token_budget: int
    used_tokens: int
    truncated: bool
    rollout_mode: str
    generated_at: datetime
```

## 10. Error model

Required typed errors include:

```text
project_not_found
workspace_not_found
project_scope_violation
revision_not_found
stale_twin_revision
stale_blueprint_revision
stale_source_revision
invalid_contract_version
migration_required
store_unavailable
store_corrupt
analysis_unavailable
collector_unavailable
context_budget_too_small
blueprint_invalid
blueprint_decision_required
convergence_unavailable
unsafe_operation_required
```

No typed error is silently replaced by empty success.

## 11. Forbidden contract behavior

- Public DTOs may not contain live database connections, private ORM rows, or file handles.
- Facades may not return mutable internal entities.
- Blueprint may not return actual implementation status without Convergence evidence.
- Digital Twin may not accept execution-authority commands.
- Convergence may not apply patches, alter PlanPool, or activate Blueprint revisions.
- Atlas adapters may not bypass the facades to read module tables directly.
