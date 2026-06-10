"""Atlas Project Intelligence Module (PI-1).

Public surface: the orchestration facade contract, the shared contract kernel, and the
disabled-by-default coordinator. Atlas consumers should depend on this facade, never on
module-private stores (architecture §3, §5.4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.project_intelligence.contracts import (
    ARCHITECTURE_BLUEPRINT_CONTRACT_VERSION,
    DIGITAL_TWIN_CONTRACT_VERSION,
    PROJECT_CONVERGENCE_CONTRACT_VERSION,
    PROJECT_INTELLIGENCE_CONTRACT_VERSION,
    ContextManifest,
    GenerationContextPackage,
    IntelligenceError,
    IntelligenceErrorCode,
    PlanningContextPackage,
    ProjectIdentity,
    ProjectIntelligenceModule,
    ProjectMode,
)

# ``facade`` imports the three sibling module facades. To keep importing the shared
# contract kernel (``agent.project_intelligence.contracts``) cycle-free — the lower
# modules import the kernel through this package — the coordinator facade is exported
# lazily (PEP 562) rather than at package import time.
if TYPE_CHECKING:  # pragma: no cover
    from agent.project_intelligence.facade import DisabledProjectIntelligenceModule


def __getattr__(name: str):
    if name == "DisabledProjectIntelligenceModule":
        from agent.project_intelligence.facade import DisabledProjectIntelligenceModule

        return DisabledProjectIntelligenceModule
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PROJECT_INTELLIGENCE_CONTRACT_VERSION",
    "DIGITAL_TWIN_CONTRACT_VERSION",
    "ARCHITECTURE_BLUEPRINT_CONTRACT_VERSION",
    "PROJECT_CONVERGENCE_CONTRACT_VERSION",
    "ContextManifest",
    "GenerationContextPackage",
    "IntelligenceError",
    "IntelligenceErrorCode",
    "PlanningContextPackage",
    "ProjectIdentity",
    "ProjectIntelligenceModule",
    "ProjectMode",
    "DisabledProjectIntelligenceModule",
]
