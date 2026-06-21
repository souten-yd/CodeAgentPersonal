"""Atlas Twin Control Plane public contracts.

These DTOs are intentionally pure and dependency-light.  They describe the
cross-product execution decision without owning execution itself: route
selection stays in Forge, context still comes from Project Intelligence / Twin,
file mutation still goes through Atlas Safe Apply, and remote publication stays
approval-bound.
"""
from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.model_forge.method_policy import (
    ContextPackageMode,
    InstructionAbstractionLevel,
    OutputProtocol,
    PatchConstructionMode,
    RepairMode,
    TaskDecompositionPolicy,
    VerificationMode,
)
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_taxonomy import ForgeRoute

ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION = "atlas.twin_control_plane.v1"


class TwinControlPlaneModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TwinInjectionLevel(IntEnum):
    NONE = 0
    SUMMARY = 1
    CONTRACTS_AND_IMPACT = 2
    CONSTRAINED_WITH_TESTS = 3
    STRICT_INTERFACE_AND_REPAIR = 4


class InstructionStyle(StrEnum):
    FREEFORM_DESIGN = "freeform_design"
    CONSTRAINED_PATCH = "constrained_patch"
    INTERFACE_FIRST = "interface_first"
    TEST_FIRST = "test_first"
    ASSUMPTION_BREAKER = "assumption_breaker"
    REPAIR_COMPASS = "repair_compass"
    BLUEPRINT_SLICE = "blueprint_slice"
    PATCH_DSL = "patch_dsl"
    AUDIT_ONLY = "audit_only"


class ModelCapabilityMode(StrEnum):
    WEAK_LOCAL = "weak_local"
    STANDARD = "standard"
    FRONTIER_ASSISTED = "frontier_assisted"
    AUDIT_ONLY = "audit_only"


class TwinConstraint(TwinControlPlaneModel):
    constraint_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    constraint_type: str = "hard"  # hard | soft | advisory
    confidence: str = "high"       # high | medium | low
    override_policy: str = "forbidden"
    refs: list[str] = Field(default_factory=list)

    @field_validator("constraint_type")
    @classmethod
    def _valid_constraint_type(cls, value: str) -> str:
        if value not in {"hard", "soft", "advisory"}:
            raise ValueError("constraint_type must be hard, soft, or advisory")
        return value

    @field_validator("confidence")
    @classmethod
    def _valid_confidence(cls, value: str) -> str:
        if value not in {"high", "medium", "low"}:
            raise ValueError("confidence must be high, medium, or low")
        return value


class GitPolicy(TwinControlPlaneModel):
    local_repo_required: bool = True
    auto_init_allowed: bool = True
    baseline_commit_required: bool = True
    local_branch_required: bool = True
    worktree_preferred: bool = True
    local_commit_required: bool = True
    fetch_pull_allowed: bool = True
    remote_publication_requires_approval: bool = True
    remote_mutation_requires_approval: bool = True


class TwinBrief(TwinControlPlaneModel):
    schema_version: str = ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION
    brief_id: str = Field(min_length=1)
    goal: str = ""
    mode: str = "existing_project"
    actual_twin_revision_id: str | None = None
    blueprint_revision_id: str | None = None
    allowed_refs: list[str] = Field(default_factory=list)
    forbidden_refs: list[str] = Field(default_factory=list)
    hard_constraints: list[TwinConstraint] = Field(default_factory=list)
    advisory_context: list[str] = Field(default_factory=list)
    contracts_to_preserve: list[str] = Field(default_factory=list)
    required_interfaces: list[str] = Field(default_factory=list)
    impacted_refs: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPolicy(TwinControlPlaneModel):
    schema_version: str = ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION
    policy_id: str = Field(min_length=1)
    route: ForgeRoute
    model_id: str = ""
    model_role: str = ""
    instruction_style: InstructionStyle = InstructionStyle.CONSTRAINED_PATCH
    model_capability_mode: ModelCapabilityMode = ModelCapabilityMode.STANDARD
    method_variant: MethodVariant | None = None
    method_fallbacks: list[MethodVariant] = Field(default_factory=list)
    instruction_abstraction_level: InstructionAbstractionLevel = InstructionAbstractionLevel.CONCRETE_STEPS
    task_decomposition_policy: TaskDecompositionPolicy = TaskDecompositionPolicy.NARROW_SLICE
    context_package_mode: ContextPackageMode = ContextPackageMode.TWIN_BRIEF
    output_protocol: OutputProtocol = OutputProtocol.STRUCTURED_JSON
    patch_construction_mode: PatchConstructionMode = PatchConstructionMode.MODEL_GENERATED
    verification_mode: VerificationMode = VerificationMode.FOCUSED_TESTS
    repair_mode: RepairMode = RepairMode.FALLBACK_METHOD
    twin_injection_level: TwinInjectionLevel = TwinInjectionLevel.CONTRACTS_AND_IMPACT
    twin_assist_mode: str = ""
    twin_assist_expected_lift: float | None = None
    twin_slot_required: bool = False
    deterministic_anchor_required: bool = False
    avoid_method_variants: list[MethodVariant] = Field(default_factory=list)
    required_twin_modules: list[str] = Field(default_factory=list)
    required_gates: list[str] = Field(default_factory=list)
    git_policy: GitPolicy = Field(default_factory=GitPolicy)
    hard_constraints: list[TwinConstraint] = Field(default_factory=list)
    advisory_context: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("twin_injection_level")
    @classmethod
    def _valid_injection_level(cls, value: TwinInjectionLevel) -> TwinInjectionLevel:
        if int(value) < 0 or int(value) > 4:
            raise ValueError("twin_injection_level must be 0..4")
        return value


def default_hard_constraints() -> list[TwinConstraint]:
    """Hard constraints shared by Twin/Forge/Git Steward policy."""
    return [
        TwinConstraint(
            constraint_id="safe_apply_required",
            text="File mutation must remain behind the Atlas Safe Apply boundary.",
            refs=["SafeApply"],
        ),
        TwinConstraint(
            constraint_id="approval_bound_remote_publication",
            text="Remote publication or remote mutation requires approval.",
            refs=["GitSteward"],
        ),
        TwinConstraint(
            constraint_id="no_test_or_gate_weakening",
            text="Do not weaken tests or gates to make an implementation appear successful.",
            refs=["TwinProof", "ContractSentinel"],
        ),
        TwinConstraint(
            constraint_id="stale_tests_are_retirement_candidates",
            text="Stale tests are marked as retirement candidates, not automatically deleted.",
            refs=["TwinProof"],
        ),
    ]
