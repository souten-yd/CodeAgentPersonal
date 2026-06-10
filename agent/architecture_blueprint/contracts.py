"""Atlas Architecture Blueprint Module — public facade contracts (PI-1).

Contract family ``atlas.architecture_blueprint.v1``. The Blueprint owns the approved
*target* design. It never marks code implemented or verified (architecture §5.2,
ADR-PI-001); only Convergence reports actual status.

Boundary rules: portable core imports only stdlib/typing/pydantic and the shared
contract kernel (``agent.project_intelligence.contracts``). It must NOT import the
Digital Twin (architecture §3: Blueprint and Digital Twin do not depend on each other),
FastAPI, UI, web/js, app.api, or PlanPool storage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import Field

from agent.project_intelligence.contracts import (
    ARCHITECTURE_BLUEPRINT_CONTRACT_VERSION,
    IntelligenceDiagnostic,
    _Frozen,
    utcnow,
)

# --- Blueprint structural models (contracts doc §4) --------------------------


class ArchitectureOption(_Frozen):
    option_id: str
    label: str = ""
    summary: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class ArchitectureDecision(_Frozen):
    decision_id: str
    topic: str = ""
    candidates: list[ArchitectureOption] = Field(default_factory=list)
    selected_option_id: str = ""
    selection_reasons: list[str] = Field(default_factory=list)
    rejected_reasons: dict[str, list[str]] = Field(default_factory=dict)
    user_constraints: list[str] = Field(default_factory=list)
    environment_constraints: list[str] = Field(default_factory=list)
    dependency_risks: list[str] = Field(default_factory=list)
    # A model may produce planner_recommendation; it may not fabricate user_decision.
    authority: Literal["user_decision", "policy_decision", "planner_recommendation"] = (
        "planner_recommendation"
    )


class BlueprintElement(_Frozen):
    element_id: str
    canonical_ref: str
    element_type: str
    name: str = ""
    description: str = ""
    mandatory: bool = True
    requirement_ids: list[str] = Field(default_factory=list)
    depends_on_element_ids: list[str] = Field(default_factory=list)
    expected_actual_refs: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    verification_contract_ids: list[str] = Field(default_factory=list)
    preserve_behaviors: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class BlueprintRelation(_Frozen):
    relation_id: str
    source_element_id: str
    target_element_id: str
    relation_type: str = "depends_on"
    properties: dict[str, Any] = Field(default_factory=dict)


class BlueprintDecisionRequest(_Frozen):
    decision_id: str
    topic: str = ""
    options: list[ArchitectureOption] = Field(default_factory=list)
    reason: str = ""


class BlueprintRevision(_Frozen):
    contract_version: str = ARCHITECTURE_BLUEPRINT_CONTRACT_VERSION
    blueprint_id: str
    revision_id: str
    project_id: str
    workspace_id: str | None = None
    parent_revision_id: str | None = None
    scope: Literal["full_project", "change_set", "repair"] = "change_set"
    source_requirement_ids: list[str] = Field(default_factory=list)
    source_twin_revision_id: str | None = None
    project_mode: str = "imported_unknown"
    status: str = "draft"
    selected_architecture: ArchitectureDecision
    elements: list[BlueprintElement] = Field(default_factory=list)
    relations: list[BlueprintRelation] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_decisions: list[BlueprintDecisionRequest] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    activated_at: datetime | None = None


# --- Requests / results ------------------------------------------------------


class BlueprintCreateRequest(_Frozen):
    project_id: str
    workspace_id: str | None = None
    scope: Literal["full_project", "change_set", "repair"] = "change_set"
    source_requirement_ids: list[str] = Field(default_factory=list)
    source_twin_revision_id: str | None = None
    project_mode: str = "imported_unknown"
    rollout_mode: str = "off"
    correlation_id: str = ""


class BlueprintRevisionRequest(_Frozen):
    project_id: str
    blueprint_id: str
    parent_revision_id: str
    reason: str = ""
    correlation_id: str = ""


class BlueprintReviewRequest(_Frozen):
    project_id: str
    blueprint_id: str
    revision_id: str


class BlueprintReviewResult(_Frozen):
    blueprint_id: str
    revision_id: str
    valid: bool = False
    unresolved_decisions: list[BlueprintDecisionRequest] = Field(default_factory=list)
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


class BlueprintActivationRequest(_Frozen):
    project_id: str
    blueprint_id: str
    revision_id: str
    correlation_id: str = ""


class BlueprintGetRequest(_Frozen):
    project_id: str
    workspace_id: str | None = None


class BlueprintGetRevisionRequest(_Frozen):
    project_id: str
    blueprint_id: str
    revision_id: str


class BlueprintResult(_Frozen):
    blueprint_id: str
    revision_id: str | None = None
    status: str = "unavailable"
    revision: BlueprintRevision | None = None
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


# --- Facade protocol ---------------------------------------------------------


@runtime_checkable
class ArchitectureBlueprintModule(Protocol):
    def create(self, request: BlueprintCreateRequest) -> BlueprintResult: ...
    def revise(self, request: BlueprintRevisionRequest) -> BlueprintResult: ...
    def review(self, request: BlueprintReviewRequest) -> BlueprintReviewResult: ...
    def activate(self, request: BlueprintActivationRequest) -> BlueprintRevision: ...
    def get_active(self, request: BlueprintGetRequest) -> BlueprintRevision | None: ...
    def get_revision(self, request: BlueprintGetRevisionRequest) -> BlueprintRevision: ...
