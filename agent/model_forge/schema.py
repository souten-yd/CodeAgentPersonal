"""Forge core schemas (PFG-5).

Pure pydantic contracts for the Model Forge: providers, models, profiles, benchmark
presets, arena candidates/scores, and the Forge execution request/result. Strict
(extra="forbid") so unknown fields are rejected. No provider execution, no external
calls, no production routing behavior — these are data shapes only.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

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
from agent.model_forge.source_policy import PrivacyMode, SourceMode
from agent.model_forge.stage_taxonomy import ForgeStage

FORGE_SCHEMA_VERSION = "forge.v1"


class ForgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceClass(StrEnum):
    LOCAL = "local"
    SELF_HOSTED = "self_hosted"
    EXTERNAL_CLOUD = "external_cloud"


class AdoptionState(StrEnum):
    NOT_APPLIED = "not_applied"
    REJECTED = "rejected"
    SELECTED_FOR_PROPOSAL = "selected_for_proposal"
    PROPOSAL_CREATED = "proposal_created"
    SAFE_APPLIED = "safe_applied"
    VERIFIED = "verified"
    PORTAL_RUN_STARTED = "portal_run_started"
    PORTAL_RUN_PASSED = "portal_run_passed"
    CAPSULE_CREATED = "capsule_created"
    PROFILE_RECORDED = "profile_recorded"


class ProviderSupport(ForgeModel):
    chat_completions: bool = False
    streaming: bool = False
    model_catalog: bool = False
    # "yes" | "no" | "model_dependent"
    tool_calling: str = "no"
    structured_outputs: str = "no"


class ProviderDescriptor(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    provider_id: str = Field(min_length=1)
    provider_type: str = Field(min_length=1)
    source_class: SourceClass
    # Disabled by default: external providers must be explicitly enabled.
    enabled: bool = False
    credential_env: str = ""
    base_url: str = ""
    supports: ProviderSupport = Field(default_factory=ProviderSupport)
    privacy_capabilities: list[PrivacyMode] = Field(default_factory=list)


class ModelDescriptor(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    model_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    display_name: str = ""
    source_class: SourceClass
    context_window: int = 0
    modalities: list[str] = Field(default_factory=lambda: ["text"])
    cost_profile: str = ""
    privacy_profile: str = ""
    capability_tags: list[str] = Field(default_factory=list)


class ModelProfile(ForgeModel):
    """Versioned, reversible per-model quality profile across Forge dimensions.
    Raw evidence is referenced, never overwritten."""

    schema_version: str = FORGE_SCHEMA_VERSION
    model_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    version: int = 1
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    sample_count: int = 0
    updated_at: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    twin_assist_scores: dict[str, float] = Field(default_factory=dict)
    twin_assist_lift: dict[str, float] = Field(default_factory=dict)
    recommended_twin_assist_mode: str = ""
    recommended_twin_injection_level: int | None = Field(default=None, ge=0, le=4)
    twin_assist_evidence_refs: list[str] = Field(default_factory=list)


class BenchmarkPreset(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    preset_id: str = Field(min_length=1)
    family_id: str = ""
    display_name: str = ""
    category: str = ""
    depth: str = "standard"
    tasks: list[str] = Field(default_factory=list)
    required_evaluators: list[str] = Field(default_factory=list)
    recommended_routes: list[ForgeRoute] = Field(default_factory=list)
    risk_level: str = "medium"
    runtime_budget_seconds: int = 600
    profile_dimensions: list[str] = Field(default_factory=list)


class ForgeUsage(ForgeModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ForgeExecutionRequest(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    request_id: str = Field(min_length=1)
    stage: ForgeStage
    route_id: ForgeRoute
    task_category: str = ""
    risk_level: str = "medium"
    source_mode: SourceMode = SourceMode.LOCAL_ONLY
    privacy_mode: PrivacyMode = PrivacyMode.NO_EXTERNAL_CODE
    candidate_models: list[str] = Field(default_factory=list)
    context_package_ref: str = ""
    output_contract: str = ""
    verification_contract: str = ""
    method_variant: MethodVariant | None = None
    method_fallbacks: list[MethodVariant] = Field(default_factory=list)
    instruction_abstraction_level: InstructionAbstractionLevel = InstructionAbstractionLevel.CONCRETE_STEPS
    task_decomposition_policy: TaskDecompositionPolicy = TaskDecompositionPolicy.NARROW_SLICE
    context_package_mode: ContextPackageMode = ContextPackageMode.TWIN_BRIEF
    output_protocol: OutputProtocol = OutputProtocol.STRUCTURED_JSON
    patch_construction_mode: PatchConstructionMode = PatchConstructionMode.MODEL_GENERATED
    verification_mode: VerificationMode = VerificationMode.FOCUSED_TESTS
    repair_mode: RepairMode = RepairMode.FALLBACK_METHOD


class ForgeExecutionResult(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    request_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    route_id: ForgeRoute
    stage: ForgeStage
    raw_output_ref: str = ""
    parsed_output_ref: str = ""
    contract_valid: bool = False
    latency_ms: int = 0
    usage: ForgeUsage = Field(default_factory=ForgeUsage)
    errors: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    method_variant: MethodVariant | None = None
    method_status: str = ""
    fallback_attempts: list[MethodVariant] = Field(default_factory=list)
    fallback_reasons: list[str] = Field(default_factory=list)


class ArenaCandidate(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    candidate_id: str = Field(min_length=1)
    arena_run_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    route_id: ForgeRoute
    preset_id: str = ""
    task_id: str = ""
    execution_result_ref: str = ""
    score_ref: str = ""
    method_variant: MethodVariant | None = None
    method_fallbacks: list[MethodVariant] = Field(default_factory=list)
    fallback_evidence_refs: list[str] = Field(default_factory=list)
    # Arena output never skips Proposal/Safe Apply: it starts un-applied.
    adoption_state: AdoptionState = AdoptionState.NOT_APPLIED


class CandidateScore(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    candidate_id: str = Field(min_length=1)
    scores: dict[str, float] = Field(default_factory=dict)
    final_score: float = 0.0
    verdict: str = ""
    blocked_reasons: list[str] = Field(default_factory=list)
    method_scores: dict[str, float] = Field(default_factory=dict)
    radar_scores: dict[str, float | None] = Field(default_factory=dict)
    unavailable_dimensions: list[str] = Field(default_factory=list)


class ModelOptimizationProfile(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    profile_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    route_fitness: dict[ForgeRoute, float] = Field(default_factory=dict)
    method_fitness: dict[MethodVariant, float] = Field(default_factory=dict)
    preferred_methods: list[MethodVariant] = Field(default_factory=list)
    fallback_methods: list[MethodVariant] = Field(default_factory=list)
    instruction_abstraction_level: InstructionAbstractionLevel = InstructionAbstractionLevel.CONCRETE_STEPS
    task_decomposition_policy: TaskDecompositionPolicy = TaskDecompositionPolicy.NARROW_SLICE
    context_package_mode: ContextPackageMode = ContextPackageMode.TWIN_BRIEF
    verification_mode: VerificationMode = VerificationMode.FOCUSED_TESTS
    evidence_refs: list[str] = Field(default_factory=list)
    unavailable_dimensions: list[str] = Field(default_factory=list)


class RoleAssignment(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    assignment_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    route: ForgeRoute
    method_variant: MethodVariant
    fallback_methods: list[MethodVariant] = Field(default_factory=list)
    twin_injection_level: int = Field(default=2, ge=0, le=4)
    instruction_abstraction_level: InstructionAbstractionLevel = InstructionAbstractionLevel.CONCRETE_STEPS
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class CandidateProposalDraft(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    draft_id: str = Field(min_length=1)
    status: str = "proposal_draft"
    candidate_id: str = Field(min_length=1)
    arena_run_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    route_id: ForgeRoute
    preset_id: str = ""
    task_id: str = ""
    stage: ForgeStage
    source_mode: SourceMode
    privacy_mode: PrivacyMode
    risk_level: str = "medium"
    evaluator_score: CandidateScore
    blocked_reasons: list[str] = Field(default_factory=list)
    required_safe_apply_steps: list[str] = Field(default_factory=list)
    required_verification_steps: list[str] = Field(default_factory=list)
    artifact_ref: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""
