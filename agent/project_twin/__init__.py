"""Atlas Project Digital Twin public contract package (PDT-1).

This package defines the versioned public contracts, types, events and ports for the
Project Digital Twin. It is intentionally free of any storage, network or framework
dependency: consumers depend only on these contracts, never on private store internals.

Public surface:
- types: enums, literals and the contract-version constant.
- versioning: contract-version constant and compatibility helpers.
- events: the twin event envelope and the initial event-type catalog.
- contracts: schemas (nodes/edges/evidence/observations/revisions/deltas/queries/context)
  and the public ports (Protocol interfaces).
"""

from __future__ import annotations

from agent.project_twin.types import (
    CONTRACT_VERSION,
    AtlasPhase,
    ObservationResult,
    TwinDerivation,
    TwinDomain,
    TwinErrorCode,
    TwinNodeStatus,
)
from agent.project_twin.versioning import (
    assert_supported_version,
    is_compatible_version,
    parse_contract_version,
)
from agent.project_twin.events import EVENT_TYPES, TwinEventEnvelope, make_event_envelope
from agent.project_twin.contracts import (
    ContextItem,
    ImpactRequest,
    ImpactResult,
    IntentDeliveryEvent,
    IntentTracePort,
    MemoryPromotionDecision,
    MemoryPromotionRequest,
    MemoryRecallRequest,
    MemoryRecallResult,
    MemorySupersedeRequest,
    ObservationIngestResult,
    PathTraceRequest,
    PathTraceResult,
    ProjectTwinPort,
    RuntimeObservation,
    RuntimeObservationPort,
    SkillActivation,
    SkillResolutionRequest,
    SkillResolutionResult,
    StaticAnalysisPort,
    StaticAnalysisRequest,
    StaticAnalysisResult,
    TwinContextPort,
    TwinContextRequest,
    TwinContextSlice,
    TwinDelta,
    TwinEdge,
    TwinEvidence,
    TwinHealth,
    TwinMemoryPort,
    TwinNode,
    TwinQuery,
    TwinQueryResult,
    TwinRevision,
    TwinSkillPort,
    TwinSnapshot,
)

__all__ = [
    "CONTRACT_VERSION",
    "AtlasPhase",
    "ObservationResult",
    "TwinDerivation",
    "TwinDomain",
    "TwinErrorCode",
    "TwinNodeStatus",
    "assert_supported_version",
    "is_compatible_version",
    "parse_contract_version",
    "EVENT_TYPES",
    "TwinEventEnvelope",
    "make_event_envelope",
    "ContextItem",
    "ImpactRequest",
    "ImpactResult",
    "IntentDeliveryEvent",
    "IntentTracePort",
    "MemoryPromotionDecision",
    "MemoryPromotionRequest",
    "MemoryRecallRequest",
    "MemoryRecallResult",
    "MemorySupersedeRequest",
    "ObservationIngestResult",
    "PathTraceRequest",
    "PathTraceResult",
    "ProjectTwinPort",
    "RuntimeObservation",
    "RuntimeObservationPort",
    "SkillActivation",
    "SkillResolutionRequest",
    "SkillResolutionResult",
    "StaticAnalysisPort",
    "StaticAnalysisRequest",
    "StaticAnalysisResult",
    "TwinContextPort",
    "TwinContextRequest",
    "TwinContextSlice",
    "TwinDelta",
    "TwinEdge",
    "TwinEvidence",
    "TwinHealth",
    "TwinMemoryPort",
    "TwinNode",
    "TwinQuery",
    "TwinQueryResult",
    "TwinRevision",
    "TwinSkillPort",
    "TwinSnapshot",
]
