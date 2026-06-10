"""Atlas Architecture Blueprint Module (PI-1).

Public surface: the Blueprint facade contract, its DTOs, and the disabled-by-default stub.
The Blueprint owns the approved target design only; it never reports actual status.
"""

from __future__ import annotations

from agent.architecture_blueprint.contracts import (
    ARCHITECTURE_BLUEPRINT_CONTRACT_VERSION,
    ArchitectureBlueprintModule,
    ArchitectureDecision,
    BlueprintElement,
    BlueprintResult,
    BlueprintRevision,
)
from agent.architecture_blueprint.facade import DisabledArchitectureBlueprintModule

__all__ = [
    "ARCHITECTURE_BLUEPRINT_CONTRACT_VERSION",
    "ArchitectureBlueprintModule",
    "ArchitectureDecision",
    "BlueprintElement",
    "BlueprintResult",
    "BlueprintRevision",
    "DisabledArchitectureBlueprintModule",
]
