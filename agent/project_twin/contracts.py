"""Versioned schemas and public ports for the Project Digital Twin (PDT-1).

Mirrors `docs/atlas_project_digital_twin_contracts.md`. No storage, network or framework
dependency: this module imports only pydantic, typing and the twin types. Consumers
depend on these contracts, never on private store internals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from agent.project_twin.types import (
    CONTRACT_VERSION,
    AtlasPhase,
    ObservationResult,
    TwinDerivation,
    TwinDomain,
    TwinErrorCode,
    TwinNodeStatus,
)


# --------------------------------------------------------------------------- #
# Core graph schemas
# --------------------------------------------------------------------------- #


class TwinNode(BaseModel):
    contract_version: str = CONTRACT_VERSION
    node_id: str
    project_id: str
    domain: TwinDomain
    node_type: str
    canonical_ref: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    source_kind: str
    source_ref: str
    source_revision: str | None = None
    content_revision: str | None = None
    derivation: TwinDerivation
    confidence: float = Field(ge=0.0, le=1.0)
    status: TwinNodeStatus
    evidence_refs: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None
    valid_from: datetime
    valid_to: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TwinEdge(BaseModel):
    contract_version: str = CONTRACT_VERSION
    edge_id: str
    project_id: str
    domain: TwinDomain
    source_node_id: str
    target_node_id: str
    edge_type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    source_kind: str
    source_ref: str
    source_revision: str | None = None
    derivation: TwinDerivation
    confidence: float = Field(ge=0.0, le=1.0)
    status: TwinNodeStatus
    evidence_refs: list[str] = Field(default_factory=list)
    valid_from: datetime
    valid_to: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TwinEvidence(BaseModel):
    contract_version: str = CONTRACT_VERSION
    evidence_id: str
    project_id: str
    evidence_type: str
    source_kind: str
    source_ref: str
    source_revision: str | None = None
    summary: str
    payload_ref: str | None = None
    content_hash: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    observed_at: datetime | None = None
    created_at: datetime


class RuntimeObservation(BaseModel):
    contract_version: str = CONTRACT_VERSION
    observation_id: str
    project_id: str
    run_id: str | None = None
    collector: str
    collector_version: str
    observation_type: str
    subject_refs: list[str] = Field(default_factory=list)
    source_revision: str | None = None
    timestamp: datetime
    result: ObservationResult
    summary: str
    payload_ref: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class TwinRevision(BaseModel):
    contract_version: str = CONTRACT_VERSION
    revision_id: str
    project_id: str
    parent_revision_id: str | None = None
    source_commit: str | None = None
    working_tree_hash: str | None = None
    trigger_type: str
    trigger_ref: str | None = None
    parser_versions: dict[str, str] = Field(default_factory=dict)
    node_upserts: int = 0
    edge_upserts: int = 0
    invalidations: int = 0
    observations_added: int = 0
    created_at: datetime


class TwinDelta(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    base_revision_id: str | None = None
    idempotency_key: str
    trigger_type: str
    trigger_ref: str | None = None
    source_commit: str | None = None
    working_tree_hash: str | None = None
    parser_versions: dict[str, str] = Field(default_factory=dict)
    nodes: list[TwinNode] = Field(default_factory=list)
    edges: list[TwinEdge] = Field(default_factory=list)
    evidence: list[TwinEvidence] = Field(default_factory=list)
    observations: list[RuntimeObservation] = Field(default_factory=list)
    invalidate_node_ids: list[str] = Field(default_factory=list)
    invalidate_edge_ids: list[str] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Store-level result schemas (carry the API response envelope fields)
# --------------------------------------------------------------------------- #


class TwinHealth(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    twin_revision_id: str | None = None
    status: str
    node_count: int = 0
    edge_count: int = 0
    stale: bool = False
    parser_versions: dict[str, str] = Field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime


class TwinSnapshot(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    twin_revision_id: str | None = None
    nodes: list[TwinNode] = Field(default_factory=list)
    edges: list[TwinEdge] = Field(default_factory=list)
    generated_at: datetime


class TwinQueryResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    twin_revision_id: str | None = None
    nodes: list[TwinNode] = Field(default_factory=list)
    edges: list[TwinEdge] = Field(default_factory=list)
    cursor: str | None = None
    truncated: bool = False
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime


class ObservationIngestResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    observation_id: str
    accepted: bool
    twin_revision_id: str | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Query / trace / impact contracts
# --------------------------------------------------------------------------- #


class TwinQuery(BaseModel):
    project_id: str
    revision_id: str | None = None
    node_types: list[str] = Field(default_factory=list)
    edge_types: list[str] = Field(default_factory=list)
    canonical_refs: list[str] = Field(default_factory=list)
    text: str | None = None
    statuses: list[TwinNodeStatus] = Field(default_factory=list)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    max_depth: int = Field(default=1, ge=0, le=5)
    limit: int = Field(default=100, ge=1, le=1000)
    cursor: str | None = None


class PathTraceRequest(BaseModel):
    project_id: str
    source_ref: str
    target_ref: str | None = None
    allowed_edge_types: list[str] = Field(default_factory=list)
    statuses: list[TwinNodeStatus] = Field(default_factory=list)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    max_depth: int = Field(default=8, ge=1, le=20)
    max_paths: int = Field(default=10, ge=1, le=50)


class TwinPath(BaseModel):
    node_refs: list[str] = Field(default_factory=list)
    edge_types: list[str] = Field(default_factory=list)
    min_confidence: float = Field(ge=0.0, le=1.0)
    contains_inferred: bool = False
    explanation: str = ""


class PathTraceResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    twin_revision_id: str | None = None
    paths: list[TwinPath] = Field(default_factory=list)
    truncated: bool = False
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime


class ImpactRequest(BaseModel):
    project_id: str
    changed_refs: list[str]
    change_kind: str
    include_domains: list[TwinDomain] = Field(default_factory=list)
    max_depth: int = Field(default=5, ge=1, le=10)
    min_confidence: float = Field(default=0.25, ge=0.0, le=1.0)
    include_historical_risks: bool = True


class ImpactItem(BaseModel):
    canonical_ref: str
    item_type: str
    status: TwinNodeStatus
    confidence: float = Field(ge=0.0, le=1.0)
    source_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str = ""


class ImpactResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    twin_revision_id: str | None = None
    direct_impacts: list[ImpactItem] = Field(default_factory=list)
    transitive_impacts: list[ImpactItem] = Field(default_factory=list)
    affected_requirements: list[ImpactItem] = Field(default_factory=list)
    behavior_paths: list[TwinPath] = Field(default_factory=list)
    side_effects: list[ImpactItem] = Field(default_factory=list)
    recommended_tests: list[ImpactItem] = Field(default_factory=list)
    past_incidents: list[ImpactItem] = Field(default_factory=list)
    uncertainty: list[dict[str, Any]] = Field(default_factory=list)
    explanation_paths: list[TwinPath] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Context contracts
# --------------------------------------------------------------------------- #


class TwinContextRequest(BaseModel):
    project_id: str
    objective: str
    phase: AtlasPhase
    plan_pool_id: str | None = None
    plan_item_id: str | None = None
    target_refs: list[str] = Field(default_factory=list)
    requested_domains: list[TwinDomain] = Field(default_factory=list)
    token_budget: int = Field(default=4000, ge=256, le=65536)
    min_confidence: float = Field(default=0.25, ge=0.0, le=1.0)
    include_unverified: bool = True
    include_contradictions: bool = True


class ContextItem(BaseModel):
    item_type: str
    canonical_ref: str
    summary: str
    status: TwinNodeStatus
    confidence: float = Field(ge=0.0, le=1.0)
    source_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    inclusion_reason: str
    estimated_tokens: int = Field(ge=0)


class TwinContextSlice(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    twin_revision_id: str | None = None
    phase: AtlasPhase
    requirements: list[ContextItem] = Field(default_factory=list)
    symbols: list[ContextItem] = Field(default_factory=list)
    paths: list[ContextItem] = Field(default_factory=list)
    side_effects: list[ContextItem] = Field(default_factory=list)
    tests: list[ContextItem] = Field(default_factory=list)
    observations: list[ContextItem] = Field(default_factory=list)
    incidents: list[ContextItem] = Field(default_factory=list)
    memories: list[ContextItem] = Field(default_factory=list)
    skills: list[ContextItem] = Field(default_factory=list)
    nexus_evidence: list[ContextItem] = Field(default_factory=list)
    preserve_behaviors: list[ContextItem] = Field(default_factory=list)
    uncertainties: list[ContextItem] = Field(default_factory=list)
    used_tokens: int = Field(default=0, ge=0)
    excluded: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = False


# --------------------------------------------------------------------------- #
# Static analysis / intent / memory / skill request-response schemas
# --------------------------------------------------------------------------- #


class StaticAnalysisRequest(BaseModel):
    project_id: str
    project_path: str
    changed_paths: list[str] = Field(default_factory=list)
    full_rebuild: bool = False
    base_revision_id: str | None = None


class StaticAnalysisResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    delta: TwinDelta
    parser_versions: dict[str, str] = Field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class IntentDeliveryEvent(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    event_type: str
    source_ref: str | None = None
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)


class MemoryRecallRequest(BaseModel):
    project_id: str
    objective: str
    limit: int = Field(default=5, ge=1, le=100)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    include_superseded: bool = False


class MemoryRecallResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    items: list[ContextItem] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class MemoryPromotionRequest(BaseModel):
    project_id: str
    candidate_ref: str
    derivation: TwinDerivation
    evidence_refs: list[str] = Field(default_factory=list)
    summary: str = ""


class MemoryPromotionDecision(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    candidate_ref: str
    promoted: bool
    reason: str
    requires_verification: bool = False


class MemorySupersedeRequest(BaseModel):
    project_id: str
    memory_ref: str
    superseded_by_ref: str | None = None
    reason: str = ""


class SkillResolutionRequest(BaseModel):
    project_id: str
    objective: str
    phase: AtlasPhase
    target_refs: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=50)


class SkillResolutionResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    skills: list[ContextItem] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class SkillActivation(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    skill_ref: str
    skill_version: str
    content_hash: str
    activation_reason: str
    phase: AtlasPhase
    outcome: str | None = None
    activated_at: datetime


# --------------------------------------------------------------------------- #
# Public ports (Protocol interfaces) — consumers depend on these, not stores
# --------------------------------------------------------------------------- #


@runtime_checkable
class ProjectTwinPort(Protocol):
    def get_health(self, project_id: str) -> TwinHealth: ...
    def get_snapshot(self, project_id: str, revision_id: str | None = None) -> TwinSnapshot: ...
    def apply_delta(self, delta: TwinDelta) -> TwinRevision: ...
    def query(self, query: TwinQuery) -> TwinQueryResult: ...
    def trace_path(self, request: PathTraceRequest) -> PathTraceResult: ...
    def assess_impact(self, request: ImpactRequest) -> ImpactResult: ...


@runtime_checkable
class StaticAnalysisPort(Protocol):
    def analyze(self, request: StaticAnalysisRequest) -> StaticAnalysisResult: ...


@runtime_checkable
class RuntimeObservationPort(Protocol):
    def ingest(self, observation: RuntimeObservation) -> ObservationIngestResult: ...


@runtime_checkable
class IntentTracePort(Protocol):
    def project(self, event: IntentDeliveryEvent) -> TwinDelta: ...


@runtime_checkable
class TwinContextPort(Protocol):
    def build_slice(self, request: TwinContextRequest) -> TwinContextSlice: ...


@runtime_checkable
class TwinMemoryPort(Protocol):
    def recall(self, request: MemoryRecallRequest) -> MemoryRecallResult: ...
    def propose_promotion(self, request: MemoryPromotionRequest) -> MemoryPromotionDecision: ...
    def supersede(self, request: MemorySupersedeRequest) -> None: ...


@runtime_checkable
class TwinSkillPort(Protocol):
    def resolve(self, request: SkillResolutionRequest) -> SkillResolutionResult: ...
    def record_activation(self, activation: SkillActivation) -> None: ...


# Typed-error alias re-export for consumers that build error responses.
__all_errors__ = TwinErrorCode
