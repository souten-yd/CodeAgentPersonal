"""Atlas Twin Control Plane integration layer.

This package contains the contracts and pure policy helpers that connect Project
Intelligence, Project Twin, Forge route/model policy, and Git Steward execution
state.  It is intentionally dependency-light so it can be used by planning,
generation, verification, and future rollout adapters without becoming an
execution authority.
"""

from agent.twin_control_plane.contracts import (
    ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION,
    ExecutionPolicy,
    GitPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinConstraint,
    TwinInjectionLevel,
)

__all__ = [
    "ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION",
    "ExecutionPolicy",
    "GitPolicy",
    "InstructionStyle",
    "ModelCapabilityMode",
    "TwinBrief",
    "TwinConstraint",
    "TwinInjectionLevel",
]
