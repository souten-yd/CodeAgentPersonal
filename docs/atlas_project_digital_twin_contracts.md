# Atlas Project Digital Twin Contracts

## 1. Contract version

Initial contract version:

```text
atlas.project_twin.v1
```

All persisted payloads and APIs include `contract_version`.

Breaking changes require a new version and compatibility policy.

## 2. Core enums

```python
TwinNodeStatus = Literal[
    "declared",
    "inferred",
    "observed",
    "verified",
    "user_approved",
    "contradicted",
    "superseded",
    "invalidated",
]

TwinDerivation = Literal[
    "canonical_projection",
    "deterministic_static",
    "heuristic_static",
    "llm_inference",
    "runtime_observation",
    "verification",
    "user_decision",
]

TwinDomain = Literal[
    "structural",
    "behavioral",
    "runtime",
    "intent_delivery",
    "learning",
]
```

## 3. Core schemas

### 3.1 TwinNode

```python
class TwinNode(BaseModel):
    contract_version: str = "atlas.project_twin.v1"
    node_id: str
    project_id: str
    domain: TwinDomain
    node_type: str
    canonical_ref: str
    label: str
    properties: dict[str, Any] = {}
    source_kind: str
    source_ref: str
    source_revision: str | None = None
    content_revision: str | None = None
    derivation: TwinDerivation
    confidence: float = Field(ge=0.0, le=1.0)
    status: TwinNodeStatus
    evidence_refs: list[str] = []
    observed_at: datetime | None = None
    valid_from: datetime
    valid_to: datetime | None = None
    created_at: datetime
    updated_at: datetime
```

Constraints:

- `(project_id, canonical_ref, valid_to IS NULL)` is unique for current facts of a compatible type;
- invalidated/superseded records remain queryable historically;
- secret values are not placed in `properties`.

### 3.2 TwinEdge

```python
class TwinEdge(BaseModel):
    contract_version: str = "atlas.project_twin.v1"
    edge_id: str
    project_id: str
    domain: TwinDomain
    source_node_id: str
    target_node_id: str
    edge_type: str
    properties: dict[str, Any] = {}
    source_kind: str
    source_ref: str
    source_revision: str | None = None
    derivation: TwinDerivation
    confidence: float = Field(ge=0.0, le=1.0)
    status: TwinNodeStatus
    evidence_refs: list[str] = []
    valid_from: datetime
    valid_to: datetime | None = None
    created_at: datetime
    updated_at: datetime
```

### 3.3 TwinEvidence

```python
class TwinEvidence(BaseModel):
    evidence_id: str
    project_id: str
    evidence_type: str
    source_kind: str
    source_ref: str
    source_revision: str | None = None
    summary: str
    payload_ref: str | None = None
    content_hash: str | None = None
    confidence: float
    observed_at: datetime | None = None
    created_at: datetime
```

Large payloads remain in canonical stores or artifact files and are referenced.

### 3.4 RuntimeObservation

```python
class RuntimeObservation(BaseModel):
    observation_id: str
    project_id: str
    run_id: str | None = None
    collector: str
    collector_version: str
    observation_type: str
    subject_refs: list[str]
    timestamp: datetime
    result: Literal["passed", "failed", "observed", "unavailable"]
    summary: str
    payload_ref: str | None = None
    evidence_ids: list[str] = []
```

### 3.5 TwinRevision

```python
class TwinRevision(BaseModel):
    revision_id: str
    project_id: str
    parent_revision_id: str | None
    source_commit: str | None
    working_tree_hash: str | None
    trigger_type: str
    trigger_ref: str | None
    parser_versions: dict[str, str] = {}
    node_upserts: int
    edge_upserts: int
    invalidations: int
    observations_added: int
    created_at: datetime
```

### 3.6 TwinDelta

```python
class TwinDelta(BaseModel):
    contract_version: str = "atlas.project_twin.v1"
    project_id: str
    base_revision_id: str | None
    idempotency_key: str
    trigger_type: str
    trigger_ref: str | None = None
    nodes: list[TwinNode] = []
    edges: list[TwinEdge] = []
    evidence: list[TwinEvidence] = []
    observations: list[RuntimeObservation] = []
    invalidate_node_ids: list[str] = []
    invalidate_edge_ids: list[str] = []
    diagnostics: list[dict[str, Any]] = []
```

## 4. Public ports

```python
class ProjectTwinPort(Protocol):
    def get_health(self, project_id: str) -> TwinHealth: ...
    def get_snapshot(self, project_id: str, revision_id: str | None = None) -> TwinSnapshot: ...
    def apply_delta(self, delta: TwinDelta) -> TwinRevision: ...
    def query(self, query: TwinQuery) -> TwinQueryResult: ...
    def trace_path(self, request: PathTraceRequest) -> PathTraceResult: ...
    def assess_impact(self, request: ImpactRequest) -> ImpactResult: ...

class StaticAnalysisPort(Protocol):
    def analyze(self, request: StaticAnalysisRequest) -> StaticAnalysisResult: ...

class RuntimeObservationPort(Protocol):
    def ingest(self, observation: RuntimeObservation) -> ObservationIngestResult: ...

class IntentTracePort(Protocol):
    def project(self, event: IntentDeliveryEvent) -> TwinDelta: ...

class TwinContextPort(Protocol):
    def build_slice(self, request: TwinContextRequest) -> TwinContextSlice: ...

class TwinMemoryPort(Protocol):
    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult: ...
    def propose_promotion(self, request: MemoryPromotionRequest) -> MemoryPromotionDecision: ...
    def supersede(self, request: MemorySupersedeRequest) -> None: ...

class TwinSkillPort(Protocol):
    def resolve(self, request: SkillResolutionRequest) -> SkillResolutionResult: ...
    def record_activation(self, activation: SkillActivation) -> None: ...
```

## 5. Query contracts

### 5.1 TwinQuery

```python
class TwinQuery(BaseModel):
    project_id: str
    revision_id: str | None = None
    node_types: list[str] = []
    edge_types: list[str] = []
    canonical_refs: list[str] = []
    text: str | None = None
    statuses: list[TwinNodeStatus] = []
    min_confidence: float = 0.0
    max_depth: int = Field(default=1, ge=0, le=5)
    limit: int = Field(default=100, ge=1, le=1000)
    cursor: str | None = None
```

### 5.2 PathTraceRequest

```python
class PathTraceRequest(BaseModel):
    project_id: str
    source_ref: str
    target_ref: str | None = None
    allowed_edge_types: list[str] = []
    statuses: list[TwinNodeStatus] = []
    min_confidence: float = 0.0
    max_depth: int = Field(default=8, ge=1, le=20)
    max_paths: int = Field(default=10, ge=1, le=50)
```

### 5.3 ImpactRequest

```python
class ImpactRequest(BaseModel):
    project_id: str
    changed_refs: list[str]
    change_kind: str
    include_domains: list[TwinDomain] = []
    max_depth: int = Field(default=5, ge=1, le=10)
    min_confidence: float = 0.25
    include_historical_risks: bool = True
```

### 5.4 ImpactResult

Must contain:

- direct impacts;
- transitive impacts;
- affected requirements;
- behavior paths;
- side effects;
- recommended tests;
- past incidents;
- uncertainty;
- explanation paths;
- source/evidence references.

## 6. Context contract

```python
AtlasPhase = Literal[
    "requirement_analysis",
    "project_investigation",
    "planning",
    "generation",
    "review",
    "verification",
    "repair",
    "final_rollup",
]

class TwinContextRequest(BaseModel):
    project_id: str
    objective: str
    phase: AtlasPhase
    plan_pool_id: str | None = None
    plan_item_id: str | None = None
    target_refs: list[str] = []
    requested_domains: list[TwinDomain] = []
    token_budget: int = Field(default=4000, ge=256, le=65536)
    min_confidence: float = 0.25
    include_unverified: bool = True
    include_contradictions: bool = True
```

```python
class ContextItem(BaseModel):
    item_type: str
    canonical_ref: str
    summary: str
    status: TwinNodeStatus
    confidence: float
    source_refs: list[str]
    evidence_refs: list[str]
    inclusion_reason: str
    estimated_tokens: int
```

```python
class TwinContextSlice(BaseModel):
    project_id: str
    twin_revision_id: str
    phase: AtlasPhase
    requirements: list[ContextItem] = []
    symbols: list[ContextItem] = []
    paths: list[ContextItem] = []
    side_effects: list[ContextItem] = []
    tests: list[ContextItem] = []
    observations: list[ContextItem] = []
    incidents: list[ContextItem] = []
    memories: list[ContextItem] = []
    skills: list[ContextItem] = []
    nexus_evidence: list[ContextItem] = []
    preserve_behaviors: list[ContextItem] = []
    uncertainties: list[ContextItem] = []
    used_tokens: int
    excluded: list[dict[str, Any]] = []
    truncated: bool = False
```

## 7. Event contracts

Every event includes:

```python
class TwinEventEnvelope(BaseModel):
    event_id: str
    event_type: str
    contract_version: str
    project_id: str
    source: str
    source_ref: str | None
    occurred_at: datetime
    idempotency_key: str
    payload: dict[str, Any]
```

Initial event types:

- `workspace.changed`
- `safe_apply.completed`
- `plan_item.completed`
- `verification.completed`
- `runtime_observation.recorded`
- `conversation.message.completed`
- `requirement.confirmed`
- `memory.promoted`
- `memory.superseded`
- `skill.registered`
- `skill.activated`
- `nexus.evidence.added`

## 8. Storage contract

Initial SQLite schema:

```text
twin_projects
twin_revisions
twin_nodes
twin_edges
twin_evidence
twin_observations
twin_delta_log
twin_projection_jobs
twin_schema_migrations
```

Mandatory database behavior:

- foreign keys enabled;
- WAL where supported;
- transaction per delta;
- idempotency unique key;
- project-scoped indexes;
- revision parent validation;
- rollback on any delta failure;
- no partial revision visibility.

## 9. API response rules

Every response includes:

- `contract_version`;
- `project_id`;
- `twin_revision_id`;
- `generated_at`;
- diagnostics when degraded;
- pagination cursor when applicable.

Errors are typed:

- `project_not_found`
- `revision_not_found`
- `stale_base_revision`
- `invalid_contract_version`
- `query_limit_exceeded`
- `collector_unavailable`
- `context_budget_too_small`
- `project_scope_violation`
- `twin_store_unavailable`
- `migration_required`

## 10. Compatibility rules

- additive optional fields are backward compatible;
- enum additions require tolerant readers;
- field removal/rename requires a new contract version;
- store migrations are explicit and tested;
- API clients send supported version or use current default;
- unknown fields are preserved where safe during proxy/round-trip operations.

## 11. Contract tests

Mandatory tests:

- node/edge/evidence serialization round-trip;
- invalid confidence/status rejected;
- deterministic canonical references;
- idempotent delta application;
- stale base revision rejection;
- transaction rollback;
- project isolation;
- context budget enforcement;
- contradiction history preservation;
- skill safety metadata cannot grant authority;
- unavailable runtime collector remains truthful.
