"""Atlas Digital Twin Module — public facade contracts (PI-1).

Contract family ``atlas.digital_twin.v2``. This is the coarse-grained public facade for
the Digital Twin Module. The existing Project Digital Twin Core v1 code
(``agent/project_twin/*``: store, static_graph, context_broker, ...) is evolved *behind*
this facade in later packages (PI-4..PI-9); it is not copied into a competing system.

Boundary rules (architecture §3, ADR-PI-014/015):
- portable core: imports only stdlib/typing/pydantic and the shared contract kernel
  (``agent.project_intelligence.contracts``) plus the v1 contracts for compatibility;
- must NOT import FastAPI, UI, web/js, app.api, PlanPool storage, or expose a private store;
- the legacy ``atlas.project_twin.v1`` contracts remain readable (see
  ``accepts_twin_contract_version`` / ``context_item_from_v1_slice``).

PI-1 ships contracts plus a safe disabled stub only; no graph/persistence logic here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from agent.project_intelligence.contracts import (
    DIGITAL_TWIN_CONTRACT_VERSION,
    LEGACY_PROJECT_TWIN_CONTRACT_VERSION,
    ContextItem,
    ContextManifest,
    IntelligenceDiagnostic,
    IntelligenceErrorCode,
    ProjectIdentity,
    RuntimeObservationRecord,
    SourceExcerpt,
    _Frozen,
    utcnow,
)

# --- Lifecycle models (contracts doc §3.1) -----------------------------------


class TwinReadiness(str, Enum):
    ABSENT = "absent"
    BUILDING = "building"
    READY = "ready"
    STALE = "stale"
    DEGRADED = "degraded"
    CORRUPT = "corrupt"
    DISABLED = "disabled"


class OpenTwinRequest(_Frozen):
    project: ProjectIdentity
    requested_capabilities: list[str] = Field(default_factory=list)
    rollout_mode: str = "off"
    correlation_id: str = ""


class TwinProjectState(_Frozen):
    project: ProjectIdentity
    readiness: TwinReadiness = TwinReadiness.DISABLED
    twin_revision_id: str | None = None
    parser_versions: dict[str, str] = Field(default_factory=dict)
    available_capabilities: list[str] = Field(default_factory=list)
    stale_reasons: list[str] = Field(default_factory=list)
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


# --- Refresh / rebuild models (contracts doc §3.2) ---------------------------


class RefreshTwinRequest(_Frozen):
    project: ProjectIdentity
    changed_paths: list[str] = Field(default_factory=list)
    trigger_type: str = "manual"
    trigger_ref: str | None = None
    expected_revision_id: str | None = None
    correlation_id: str = ""
    full_rebuild: bool = False


class RebuildTwinRequest(_Frozen):
    project: ProjectIdentity
    reason: str = "explicit_maintenance"
    correlation_id: str = ""


class TwinRefreshResult(_Frozen):
    project_id: str
    workspace_id: str
    previous_revision_id: str | None = None
    twin_revision_id: str | None = None
    readiness: TwinReadiness = TwinReadiness.DISABLED
    changed_node_count: int = 0
    changed_edge_count: int = 0
    invalidation_count: int = 0
    affected_refs: list[str] = Field(default_factory=list)
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


# --- Event envelope (contracts doc §3.3) -------------------------------------

PROJECT_EVENT_TYPES: tuple[str, ...] = (
    "project.opened",
    "workspace.changed",
    "conversation.message.completed",
    "requirement.confirmed",
    "requirement.revised",
    "plan.created",
    "plan.revised",
    "plan_item.started",
    "plan_item.completed",
    "plan_item.failed",
    "proposal.generated",
    "proposal.approved",
    "proposal.rejected",
    "safe_apply.completed",
    "verification.started",
    "verification.completed",
    "runtime_observation.recorded",
    "memory.promoted",
    "memory.superseded",
    "skill.registered",
    "skill.activated",
    "skill.outcome.recorded",
    "nexus.evidence.added",
)


class ProjectEventEnvelope(_Frozen):
    contract_version: str = DIGITAL_TWIN_CONTRACT_VERSION
    event_id: str
    event_type: str
    project_id: str
    workspace_id: str
    source: str = ""
    source_ref: str | None = None
    source_revision: str | None = None
    occurred_at: datetime = Field(default_factory=utcnow)
    idempotency_key: str = ""
    correlation_id: str = ""
    causation_event_id: str | None = None
    run_id: str | None = None
    plan_pool_id: str | None = None
    plan_item_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TwinEventResult(_Frozen):
    project_id: str
    workspace_id: str
    event_id: str
    accepted: bool = False
    duplicate: bool = False
    twin_revision_id: str | None = None
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


# --- Runtime ingest ----------------------------------------------------------


class RuntimeIngestRequest(_Frozen):
    project: ProjectIdentity
    observations: list[RuntimeObservationRecord] = Field(default_factory=list)
    correlation_id: str = ""


class RuntimeIngestResult(_Frozen):
    project_id: str
    workspace_id: str
    ingested_count: int = 0
    unavailable_count: int = 0
    twin_revision_id: str | None = None
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


# --- Query models (contracts doc §3.4) ---------------------------------------


class TwinQueryKind(str, Enum):
    SNAPSHOT = "snapshot"
    SEARCH = "search"
    PATH = "path"
    IMPACT = "impact"
    TEST_SELECTION = "test_selection"
    DELIVERY_TRACE = "delivery_trace"
    SOURCE_CONTEXT = "source_context"


class TwinQueryRequest(_Frozen):
    project_id: str
    workspace_id: str
    revision_id: str | None = None
    kind: TwinQueryKind = TwinQueryKind.SNAPSHOT
    refs: list[str] = Field(default_factory=list)
    text: str | None = None
    domains: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    max_depth: int = 5
    limit: int = 100
    options: dict[str, Any] = Field(default_factory=dict)


class TwinQueryResultItem(_Frozen):
    ref: str
    kind: str = ""
    summary: str = ""
    status: str = "inferred"
    confidence: float = 0.0
    source_refs: list[str] = Field(default_factory=list)


class TwinQueryResult(_Frozen):
    """Stable summary package — never a SQLite row or private graph object."""

    project_id: str
    workspace_id: str
    twin_revision_id: str | None = None
    kind: TwinQueryKind = TwinQueryKind.SNAPSHOT
    items: list[TwinQueryResultItem] = Field(default_factory=list)
    truncated: bool = False
    next_cursor: str | None = None
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


# --- Context package (contracts doc §3.5) ------------------------------------


class TwinContextRequest(_Frozen):
    project_id: str
    workspace_id: str
    objective: str = ""
    phase: str = ""
    target_refs: list[str] = Field(default_factory=list)
    token_budget: int = 8000
    min_confidence: float = 0.25
    include_unverified: bool = True
    include_contradictions: bool = True


class TwinContextPackage(_Frozen):
    contract_version: str = DIGITAL_TWIN_CONTRACT_VERSION
    project_id: str
    workspace_id: str
    twin_revision_id: str | None = None
    phase: str = ""
    requirements: list[ContextItem] = Field(default_factory=list)
    symbols: list[ContextItem] = Field(default_factory=list)
    interfaces: list[ContextItem] = Field(default_factory=list)
    behavior_paths: list[ContextItem] = Field(default_factory=list)
    state_and_events: list[ContextItem] = Field(default_factory=list)
    side_effects: list[ContextItem] = Field(default_factory=list)
    tests: list[ContextItem] = Field(default_factory=list)
    runtime_evidence: list[ContextItem] = Field(default_factory=list)
    incidents: list[ContextItem] = Field(default_factory=list)
    memories: list[ContextItem] = Field(default_factory=list)
    skills: list[ContextItem] = Field(default_factory=list)
    nexus_evidence: list[ContextItem] = Field(default_factory=list)
    preserve_behaviors: list[ContextItem] = Field(default_factory=list)
    uncertainties: list[ContextItem] = Field(default_factory=list)
    source_material: list[SourceExcerpt] = Field(default_factory=list)
    manifest: ContextManifest


class TwinHealthRequest(_Frozen):
    project_id: str
    workspace_id: str


class TwinHealthReport(_Frozen):
    project_id: str
    workspace_id: str
    readiness: TwinReadiness = TwinReadiness.DISABLED
    twin_revision_id: str | None = None
    node_count: int = 0
    edge_count: int = 0
    diagnostics: list[IntelligenceDiagnostic] = Field(default_factory=list)


# --- Facade protocol ---------------------------------------------------------


@runtime_checkable
class DigitalTwinModule(Protocol):
    def open_project(self, request: OpenTwinRequest) -> TwinProjectState: ...
    def refresh(self, request: RefreshTwinRequest) -> TwinRefreshResult: ...
    def rebuild(self, request: RebuildTwinRequest) -> TwinRefreshResult: ...
    def ingest_event(self, event: ProjectEventEnvelope) -> TwinEventResult: ...
    def ingest_runtime(self, request: RuntimeIngestRequest) -> RuntimeIngestResult: ...
    def query(self, request: TwinQueryRequest) -> TwinQueryResult: ...
    def build_context(self, request: TwinContextRequest) -> TwinContextPackage: ...
    def health(self, request: TwinHealthRequest) -> TwinHealthReport: ...


# --- v1 compatibility readers ------------------------------------------------


def accepts_twin_contract_version(version: str) -> bool:
    """The facade reads both the legacy v1 and the new v2 twin contract families."""
    return version in (LEGACY_PROJECT_TWIN_CONTRACT_VERSION, DIGITAL_TWIN_CONTRACT_VERSION)


def context_item_from_v1_slice_item(item: Any) -> ContextItem:
    """Adapt a Core v1 ``ContextItem`` (atlas.project_twin.v1) into the v2 kernel item.

    Accepts either a pydantic v1 ``ContextItem`` or a mapping with the v1 field names.
    Unknown fields are ignored; missing fields fall back to safe defaults. This never
    upgrades status/confidence — a v1 inferred fact stays inferred (ADR-PI-006/013).
    """
    def get(name: str, default: Any) -> Any:
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)

    return ContextItem(
        ref=str(get("ref", get("node_id", ""))),
        kind=str(get("kind", get("node_type", "")) or ""),
        summary=str(get("summary", "") or ""),
        status=str(get("status", "inferred") or "inferred"),
        confidence=float(get("confidence", 0.0) or 0.0),
        source_refs=list(get("source_refs", []) or []),
        inclusion_reason=str(get("inclusion_reason", get("reason", "")) or ""),
    )


# --- Safe disabled stub (PI-1: no graph/persistence logic) -------------------


def _disabled_diag(message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(
        code=IntelligenceErrorCode.ANALYSIS_UNAVAILABLE,
        message=message,
        severity="info",
    )


def _disabled_manifest(project_id: str, workspace_id: str, phase: str, budget: int) -> ContextManifest:
    return ContextManifest(
        manifest_id="disabled",
        project_id=project_id,
        workspace_id=workspace_id,
        phase=phase,
        token_budget=budget,
        used_tokens=0,
        truncated=False,
        rollout_mode="off",
    )


class DisabledDigitalTwinModule:
    """Disabled-by-default Digital Twin facade.

    Returns explicit DISABLED/unavailable results and never fabricates a twin revision,
    a passed observation, or graph content. It holds no store reference, so it cannot
    leak private persistence (architecture §3, ADR-PI-015). Real wiring arrives in
    PI-3/PI-4 behind the rollout flag.
    """

    rollout_mode = "off"

    def open_project(self, request: OpenTwinRequest) -> TwinProjectState:
        return TwinProjectState(
            project=request.project,
            readiness=TwinReadiness.DISABLED,
            diagnostics=[_disabled_diag("digital twin disabled (rollout off)")],
        )

    def refresh(self, request: RefreshTwinRequest) -> TwinRefreshResult:
        return TwinRefreshResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            readiness=TwinReadiness.DISABLED,
            diagnostics=[_disabled_diag("digital twin disabled (rollout off)")],
        )

    def rebuild(self, request: RebuildTwinRequest) -> TwinRefreshResult:
        return TwinRefreshResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            readiness=TwinReadiness.DISABLED,
            diagnostics=[_disabled_diag("digital twin disabled (rollout off)")],
        )

    def ingest_event(self, event: ProjectEventEnvelope) -> TwinEventResult:
        return TwinEventResult(
            project_id=event.project_id,
            workspace_id=event.workspace_id,
            event_id=event.event_id,
            accepted=False,
            diagnostics=[_disabled_diag("digital twin disabled (rollout off)")],
        )

    def ingest_runtime(self, request: RuntimeIngestRequest) -> RuntimeIngestResult:
        # Unavailable is never converted to passed (ADR-PI-013).
        unavailable = sum(1 for o in request.observations if o.result == "unavailable")
        return RuntimeIngestResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            ingested_count=0,
            unavailable_count=unavailable,
            diagnostics=[_disabled_diag("digital twin disabled (rollout off)")],
        )

    def query(self, request: TwinQueryRequest) -> TwinQueryResult:
        return TwinQueryResult(
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            kind=request.kind,
            items=[],
            diagnostics=[_disabled_diag("digital twin disabled (rollout off)")],
        )

    def build_context(self, request: TwinContextRequest) -> TwinContextPackage:
        return TwinContextPackage(
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            phase=request.phase,
            manifest=_disabled_manifest(
                request.project_id, request.workspace_id, request.phase, request.token_budget
            ),
        )

    def health(self, request: TwinHealthRequest) -> TwinHealthReport:
        return TwinHealthReport(
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            readiness=TwinReadiness.DISABLED,
            diagnostics=[_disabled_diag("digital twin disabled (rollout off)")],
        )
