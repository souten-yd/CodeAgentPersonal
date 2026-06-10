"""Atlas Convergence Module — public facade contracts (PI-1).

Contract family ``atlas.project_convergence.v1``. Convergence compares one Blueprint
revision against one Actual Twin revision and returns gaps and a bounded next-action
*recommendation*. It never mutates the workspace, PlanPool or Blueprint, and never
applies its decision (architecture §5.3, ADR-PI-003/009).

Boundary rules: portable core imports only stdlib/typing/pydantic and the shared
contract kernel. It may consume public Blueprint/Digital Twin snapshots by *reference id*
(it does not need to import their modules for PI-1). It must NOT import SQLite private
tables, FastAPI, UI, web/js, app.api, or PlanPool storage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import Field

from agent.project_intelligence.contracts import (
    PROJECT_CONVERGENCE_CONTRACT_VERSION,
    GapSummary,
    IntelligenceDiagnostic,
    _Frozen,
    utcnow,
)

# --- Evaluation request (contracts doc §5.1) ---------------------------------


class ConvergenceRequest(_Frozen):
    project_id: str
    workspace_id: str
    blueprint_revision_id: str
    actual_twin_revision_id: str
    requirement_revision_id: str | None = None
    changed_refs: list[str] = Field(default_factory=list)
    verification_refs: list[str] = Field(default_factory=list)
    full_evaluation: bool = False


# --- Element result (contracts doc §5.2) -------------------------------------


class ConvergenceMismatch(_Frozen):
    dimension: str
    expected_ref: str | None = None
    actual_ref: str | None = None
    detail: str = ""


ElementState = Literal[
    "absent", "partial", "materialized", "observed", "verified",
    "divergent", "blocked", "stale",
]


class ElementConvergenceResult(_Frozen):
    blueprint_element_id: str
    state: ElementState = "absent"
    matched_actual_refs: list[str] = Field(default_factory=list)
    missing_actual_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    mismatches: list[ConvergenceMismatch] = Field(default_factory=list)
    confidence: float = 0.0


# --- Report and decision (contracts doc §5.3) --------------------------------


class ConvergenceReport(_Frozen):
    contract_version: str = PROJECT_CONVERGENCE_CONTRACT_VERSION
    report_id: str
    project_id: str
    workspace_id: str
    blueprint_revision_id: str
    actual_twin_revision_id: str
    element_results: list[ElementConvergenceResult] = Field(default_factory=list)
    mandatory_gaps: list[GapSummary] = Field(default_factory=list)
    optional_gaps: list[GapSummary] = Field(default_factory=list)
    stale_evidence: list[str] = Field(default_factory=list)
    requirement_coverage: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)


ConvergenceAction = Literal[
    "continue", "complete", "repair_current_item", "replan_downstream",
    "revise_blueprint", "request_critical_decision", "halt_unsafe",
]


class ConvergenceDecisionRequest(_Frozen):
    project_id: str
    workspace_id: str
    report_id: str
    correlation_id: str = ""


class ConvergenceDecision(_Frozen):
    action: ConvergenceAction = "halt_unsafe"
    reason_codes: list[str] = Field(default_factory=list)
    affected_blueprint_elements: list[str] = Field(default_factory=list)
    affected_plan_items: list[str] = Field(default_factory=list)
    mandatory_gaps: list[str] = Field(default_factory=list)
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


class ConvergenceGetRequest(_Frozen):
    project_id: str
    workspace_id: str
    blueprint_revision_id: str | None = None


# --- Facade protocol ---------------------------------------------------------


@runtime_checkable
class ConvergenceModule(Protocol):
    def evaluate(self, request: ConvergenceRequest) -> ConvergenceReport: ...
    def decide(self, request: ConvergenceDecisionRequest) -> ConvergenceDecision: ...
    def get_latest(self, request: ConvergenceGetRequest) -> ConvergenceReport | None: ...
