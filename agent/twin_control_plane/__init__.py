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
from agent.twin_control_plane.genesis import (
    GenesisClassification,
    GenesisKind,
    GenesisRun,
    adapt_greenfield_session,
    classify_genesis,
    safe_apply_required_for_slice,
)
from agent.twin_control_plane.instruction_compiler import CompiledInstruction, compile_model_instruction
from agent.twin_control_plane.integration_impact_gate import (
    IntegrationImpactReport,
    IntegrationPoint,
    assess_integration_impact,
)
from agent.twin_control_plane.interface_first_generator import (
    InterfaceFirstPlan,
    InterfaceFirstSection,
    InterfaceSectionKind,
    apply_interface_first_plan,
    generate_interface_first_plan,
)
from agent.twin_control_plane.no_data_bootstrap_gate import (
    BootstrapCondition,
    BootstrapRequirement,
    NoDataBootstrapAssessment,
    evaluate_no_data_bootstrap,
)

__all__ = [
    "ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION",
    "BootstrapCondition",
    "BootstrapRequirement",
    "CompiledInstruction",
    "ExecutionPolicy",
    "GenesisClassification",
    "GenesisKind",
    "GenesisRun",
    "GitPolicy",
    "InstructionStyle",
    "IntegrationImpactReport",
    "IntegrationPoint",
    "InterfaceFirstPlan",
    "InterfaceFirstSection",
    "InterfaceSectionKind",
    "ModelCapabilityMode",
    "NoDataBootstrapAssessment",
    "TwinBrief",
    "TwinConstraint",
    "TwinInjectionLevel",
    "adapt_greenfield_session",
    "apply_interface_first_plan",
    "assess_integration_impact",
    "classify_genesis",
    "compile_model_instruction",
    "evaluate_no_data_bootstrap",
    "generate_interface_first_plan",
    "safe_apply_required_for_slice",
]
