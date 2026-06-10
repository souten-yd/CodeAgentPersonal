"""Atlas Project Intelligence — public contract kernel and facade contracts (PI-1).

This module is the dependency-neutral *contract kernel* for the whole Project
Intelligence system plus the public contracts for the Project Intelligence Module.

Portability (ADR-PI-014): it imports only stdlib, typing and pydantic v2 (the schema
library already used by the project). It must NOT import FastAPI, UI, web/js, app.api,
PlanPool storage, or any module-private store. The lower module facades
(``project_twin``, ``architecture_blueprint``, ``project_convergence``) import the shared
kernel types from here; this module never imports their facades, so there is no cycle.

PI-1 scope: versioned public contracts and coarse facades only. No analysis, persistence
or orchestration logic is implemented beyond safe disabled/unavailable stubs (see
``facade.py``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

# --- Contract versions -------------------------------------------------------

PROJECT_INTELLIGENCE_CONTRACT_VERSION = "atlas.project_intelligence.v1"
DIGITAL_TWIN_CONTRACT_VERSION = "atlas.digital_twin.v2"
ARCHITECTURE_BLUEPRINT_CONTRACT_VERSION = "atlas.architecture_blueprint.v1"
PROJECT_CONVERGENCE_CONTRACT_VERSION = "atlas.project_convergence.v1"

# The legacy Project Digital Twin Core v1 contract family remains readable during
# migration (see ``project_twin.facade.accepts_twin_contract_version``).
LEGACY_PROJECT_TWIN_CONTRACT_VERSION = "atlas.project_twin.v1"


def utcnow() -> datetime:
    """Deterministic, timezone-aware now() seam (overridable in tests)."""
    return datetime.now(timezone.utc)


class _Frozen(BaseModel):
    """Public DTO base: immutable, deterministic, and free of live resources.

    Forbidden contract behavior (contracts doc §11) is structurally discouraged here:
    public DTOs carry only serializable data, never connections, ORM rows or handles.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Error model (contracts doc §10) -----------------------------------------


class IntelligenceErrorCode(str, Enum):
    PROJECT_NOT_FOUND = "project_not_found"
    WORKSPACE_NOT_FOUND = "workspace_not_found"
    PROJECT_SCOPE_VIOLATION = "project_scope_violation"
    REVISION_NOT_FOUND = "revision_not_found"
    STALE_TWIN_REVISION = "stale_twin_revision"
    STALE_BLUEPRINT_REVISION = "stale_blueprint_revision"
    STALE_SOURCE_REVISION = "stale_source_revision"
    INVALID_CONTRACT_VERSION = "invalid_contract_version"
    MIGRATION_REQUIRED = "migration_required"
    STORE_UNAVAILABLE = "store_unavailable"
    STORE_CORRUPT = "store_corrupt"
    ANALYSIS_UNAVAILABLE = "analysis_unavailable"
    COLLECTOR_UNAVAILABLE = "collector_unavailable"
    CONTEXT_BUDGET_TOO_SMALL = "context_budget_too_small"
    BLUEPRINT_INVALID = "blueprint_invalid"
    BLUEPRINT_DECISION_REQUIRED = "blueprint_decision_required"
    CONVERGENCE_UNAVAILABLE = "convergence_unavailable"
    UNSAFE_OPERATION_REQUIRED = "unsafe_operation_required"


class IntelligenceDiagnostic(_Frozen):
    """An explicit, typed diagnostic. Never silently replaced by empty success."""

    code: IntelligenceErrorCode
    message: str
    refs: list[str] = Field(default_factory=list)
    severity: str = "info"


class IntelligenceError(Exception):
    """Raised for unrecoverable contract violations. Carries a typed code."""

    def __init__(self, code: IntelligenceErrorCode, message: str = "") -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}" if message else code.value)


# --- Common identity (contracts doc §2) --------------------------------------


class ProjectIdentity(_Frozen):
    project_id: str
    workspace_id: str
    project_path: str
    repository_identity: str | None = None
    branch_or_worktree: str | None = None
    source_revision: str | None = None
    working_tree_hash: str = ""


class ProjectMode(str, Enum):
    EMPTY = "empty"
    GREENFIELD_PARTIAL = "greenfield_partial"
    EXISTING = "existing"
    GENERATED_UNVERIFIED = "generated_unverified"
    IMPORTED_UNKNOWN = "imported_unknown"


# --- Shared context primitives (used by twin + project intelligence) ----------


class ContextItem(_Frozen):
    ref: str
    kind: str
    summary: str = ""
    status: str = "inferred"
    confidence: float = 0.0
    source_refs: list[str] = Field(default_factory=list)
    inclusion_reason: str = ""


class SourceExcerpt(_Frozen):
    ref: str
    path: str
    start_line: int = 0
    end_line: int = 0
    excerpt: str = ""
    source_revision: str | None = None


class ContextManifest(_Frozen):
    manifest_id: str
    project_id: str
    workspace_id: str
    phase: str
    actual_twin_revision_id: str | None = None
    blueprint_revision_id: str | None = None
    convergence_report_id: str | None = None
    included_refs: list[str] = Field(default_factory=list)
    excluded_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    uncertainty_refs: list[str] = Field(default_factory=list)
    source_revisions: dict[str, str] = Field(default_factory=dict)
    token_budget: int = 0
    used_tokens: int = 0
    truncated: bool = False
    rollout_mode: str = "off"
    generated_at: datetime = Field(default_factory=utcnow)


# --- Runtime observation contract (contracts doc §8) -------------------------


class RuntimeObservationRecord(_Frozen):
    observation_id: str
    project_id: str
    workspace_id: str
    run_id: str | None = None
    collector: str = ""
    collector_version: str = ""
    observation_type: str = ""
    subject_refs: list[str] = Field(default_factory=list)
    source_revision: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)
    result: str = "unavailable"  # passed | failed | observed | unavailable
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    payload_ref: str | None = None


# --- Summary DTOs used by planning/generation packages (contracts doc §6) -----


class ProjectStateSummary(_Frozen):
    project_id: str
    workspace_id: str
    readiness: str = "disabled"
    twin_revision_id: str | None = None
    available_capabilities: list[str] = Field(default_factory=list)
    stale_reasons: list[str] = Field(default_factory=list)


class RequirementSummary(_Frozen):
    requirement_id: str
    text: str = ""
    status: str = "unknown"
    constraint_ids: list[str] = Field(default_factory=list)


class ArchitectureSummary(_Frozen):
    label: str = ""
    components: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class ImpactSummary(_Frozen):
    ref: str
    impacted_refs: list[str] = Field(default_factory=list)
    recommended_tests: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class GapSummary(_Frozen):
    gap_id: str
    blueprint_element_id: str | None = None
    description: str = ""
    mandatory: bool = True
    missing_refs: list[str] = Field(default_factory=list)


class TestSummary(_Frozen):
    ref: str
    name: str = ""
    reason: str = ""


class DecisionSummary(_Frozen):
    decision_id: str
    topic: str = ""
    authority: str = "planner_recommendation"
    options: list[str] = Field(default_factory=list)


class UncertaintySummary(_Frozen):
    ref: str
    reason: str = ""
    severity: str = "info"


class SourceFileContext(_Frozen):
    path: str
    ref: str
    source_revision: str | None = None
    excerpts: list[SourceExcerpt] = Field(default_factory=list)


class BlueprintContractSummary(_Frozen):
    element_id: str
    canonical_ref: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    verification_contract_ids: list[str] = Field(default_factory=list)


class SymbolSummary(_Frozen):
    ref: str
    name: str = ""
    kind: str = ""
    parent: str = ""


class InterfaceSummary(_Frozen):
    ref: str
    name: str = ""
    signature: str = ""


class BehaviorPathSummary(_Frozen):
    path_id: str
    steps: list[str] = Field(default_factory=list)
    inferred: bool = True


class VerificationRequirement(_Frozen):
    requirement_id: str
    description: str = ""
    commands: list[str] = Field(default_factory=list)
    must_observe: list[str] = Field(default_factory=list)


# --- Project Intelligence requests/results (contracts doc §6) ----------------


class PrepareProjectRequest(_Frozen):
    project: ProjectIdentity
    rollout_mode: str = "off"
    correlation_id: str = ""


class ProjectIntelligenceState(_Frozen):
    project_id: str
    workspace_id: str
    project_mode: ProjectMode = ProjectMode.IMPORTED_UNKNOWN
    rollout_mode: str = "off"
    twin_readiness: str = "disabled"
    actual_twin_revision_id: str | None = None
    blueprint_revision_id: str | None = None
    available_capabilities: list[str] = Field(default_factory=list)
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


class PlanningContextRequest(_Frozen):
    project: ProjectIdentity
    objective: str
    plan_pool_id: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    target_refs: list[str] = Field(default_factory=list)
    token_budget: int = 8000
    rollout_mode: str = "off"
    correlation_id: str = ""


class PlanningContextPackage(_Frozen):
    contract_version: str = PROJECT_INTELLIGENCE_CONTRACT_VERSION
    project_state: ProjectStateSummary
    project_mode: ProjectMode = ProjectMode.IMPORTED_UNKNOWN
    actual_twin_revision_id: str | None = None
    blueprint_revision_id: str | None = None
    convergence_report_id: str | None = None
    requirements: list[RequirementSummary] = Field(default_factory=list)
    current_architecture: ArchitectureSummary = Field(default_factory=ArchitectureSummary)
    target_architecture: ArchitectureSummary | None = None
    impacted_areas: list[ImpactSummary] = Field(default_factory=list)
    unresolved_gaps: list[GapSummary] = Field(default_factory=list)
    relevant_tests: list[TestSummary] = Field(default_factory=list)
    critical_decisions: list[DecisionSummary] = Field(default_factory=list)
    uncertainties: list[UncertaintySummary] = Field(default_factory=list)
    context_manifest: ContextManifest


class GenerationContextRequest(_Frozen):
    project: ProjectIdentity
    plan_pool_id: str
    plan_item_id: str
    target_refs: list[str] = Field(default_factory=list)
    token_budget: int = 8000
    rollout_mode: str = "off"
    correlation_id: str = ""


class GenerationContextPackage(_Frozen):
    contract_version: str = PROJECT_INTELLIGENCE_CONTRACT_VERSION
    project_id: str
    workspace_id: str
    plan_pool_id: str
    plan_item_id: str
    actual_twin_revision_id: str | None = None
    blueprint_revision_id: str | None = None
    convergence_report_id: str | None = None
    target_files: list[SourceFileContext] = Field(default_factory=list)
    blueprint_contracts: list[BlueprintContractSummary] = Field(default_factory=list)
    actual_symbols: list[SymbolSummary] = Field(default_factory=list)
    required_interfaces: list[InterfaceSummary] = Field(default_factory=list)
    behavior_paths: list[BehaviorPathSummary] = Field(default_factory=list)
    preserve_behaviors: list[str] = Field(default_factory=list)
    convergence_gaps: list[GapSummary] = Field(default_factory=list)
    verification_requirements: list[VerificationRequirement] = Field(default_factory=list)
    prohibited_divergences: list[str] = Field(default_factory=list)
    context_manifest: ContextManifest


class ApplyResultRequest(_Frozen):
    project: ProjectIdentity
    plan_pool_id: str
    plan_item_id: str
    applied_refs: list[str] = Field(default_factory=list)
    blueprint_revision_id: str | None = None
    base_revision: str | None = None
    new_source_revision: str | None = None
    success: bool = False
    correlation_id: str = ""


class PostApplyIntelligenceResult(_Frozen):
    project_id: str
    workspace_id: str
    accepted: bool = False
    refresh_requested: bool = False
    twin_revision_id: str | None = None
    convergence_report_id: str | None = None
    convergence_decision: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


class VerificationResultRequest(_Frozen):
    project: ProjectIdentity
    plan_pool_id: str
    plan_item_id: str
    observations: list[RuntimeObservationRecord] = Field(default_factory=list)
    blueprint_revision_id: str | None = None
    actual_twin_revision_id: str | None = None
    source_revision: str | None = None
    plan_pool_revision: str | None = None
    correlation_id: str = ""


class PostVerificationIntelligenceResult(_Frozen):
    project_id: str
    workspace_id: str
    accepted: bool = False
    reconciled: bool = False
    convergence_requested: bool = False
    twin_revision_id: str | None = None
    convergence_report_id: str | None = None
    convergence_decision: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


class ProgressRequest(_Frozen):
    project: ProjectIdentity
    plan_pool_id: str | None = None
    correlation_id: str = ""


class ProjectProgressResult(_Frozen):
    project_id: str
    workspace_id: str
    requirement_coverage: dict[str, Any] = Field(default_factory=dict)
    convergence_report_id: str | None = None
    mandatory_gaps: list[GapSummary] = Field(default_factory=list)
    complete: bool = False
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


@runtime_checkable
class ProjectIntelligenceModule(Protocol):
    """Coarse-grained orchestration facade — the preferred Atlas integration surface.

    It coordinates the Digital Twin, Blueprint and Convergence facades without exposing
    their private storage. It is never an execution authority (ADR-PI-003).
    """

    def prepare_project(self, request: PrepareProjectRequest) -> ProjectIntelligenceState: ...
    def prepare_planning_context(self, request: PlanningContextRequest) -> PlanningContextPackage: ...
    def prepare_generation_context(self, request: GenerationContextRequest) -> GenerationContextPackage: ...
    def record_apply_result(self, request: ApplyResultRequest) -> PostApplyIntelligenceResult: ...
    def record_verification_result(self, request: VerificationResultRequest) -> PostVerificationIntelligenceResult: ...
    def evaluate_progress(self, request: ProgressRequest) -> ProjectProgressResult: ...
