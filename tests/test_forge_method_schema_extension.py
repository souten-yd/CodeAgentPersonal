from __future__ import annotations

import pytest
from pydantic import ValidationError

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
from agent.model_forge.schema import (
    ArenaCandidate,
    CandidateScore,
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ModelOptimizationProfile,
    RoleAssignment,
)
from agent.model_forge.stage_taxonomy import ForgeStage
from agent.twin_control_plane.contracts import ExecutionPolicy


def test_legacy_forge_json_migrates_through_additive_defaults():
    request = ForgeExecutionRequest.model_validate(
        {
            "schema_version": "forge.v1",
            "request_id": "legacy-request",
            "stage": "patch_generation",
            "route_id": "patch_dsl",
        }
    )
    result = ForgeExecutionResult.model_validate(
        {
            "schema_version": "forge.v1",
            "request_id": "legacy-request",
            "provider_id": "local",
            "model_id": "model",
            "route_id": "patch_dsl",
            "stage": "patch_generation",
        }
    )
    candidate = ArenaCandidate.model_validate(
        {
            "schema_version": "forge.v1",
            "candidate_id": "candidate",
            "arena_run_id": "run",
            "model_id": "model",
            "provider_id": "local",
            "route_id": "patch_dsl",
        }
    )
    score = CandidateScore.model_validate(
        {"schema_version": "forge.v1", "candidate_id": "candidate"}
    )

    assert request.method_variant is None
    assert result.fallback_attempts == []
    assert candidate.method_fallbacks == []
    assert score.radar_scores == {}
    assert request.schema_version == result.schema_version == "forge.v1"


def test_execution_policy_remains_backward_compatible():
    policy = ExecutionPolicy(policy_id="policy", route=ForgeRoute.DIRECT_PATCH)
    assert policy.method_variant is None
    assert policy.method_fallbacks == []
    assert policy.task_decomposition_policy == TaskDecompositionPolicy.NARROW_SLICE
    assert policy.instruction_abstraction_level == InstructionAbstractionLevel.CONCRETE_STEPS


def test_method_fields_roundtrip_on_existing_dtos():
    request = ForgeExecutionRequest(
        request_id="request",
        stage=ForgeStage.PATCH_GENERATION,
        route_id=ForgeRoute.PATCH_DSL,
        method_variant=MethodVariant.EDIT_INTENT_LIST,
        method_fallbacks=[MethodVariant.ANCHORED_EDIT_BLOCK],
        context_package_mode=ContextPackageMode.IMPACT_SLICE,
        output_protocol=OutputProtocol.EDIT_INTENT_LIST,
        patch_construction_mode=PatchConstructionMode.DETERMINISTIC_TEXT,
        verification_mode=VerificationMode.AFFECTED_TESTS,
        repair_mode=RepairMode.REPAIR_COMPASS,
    )
    assert ForgeExecutionRequest.model_validate(request.model_dump(mode="json")) == request


def test_optimization_profile_and_role_assignment_are_strict():
    profile = ModelOptimizationProfile(
        profile_id="profile",
        model_id="model",
        provider_id="local",
        route_fitness={ForgeRoute.PATCH_DSL: 0.9},
        method_fitness={MethodVariant.EDIT_INTENT_LIST: 0.8},
    )
    assignment = RoleAssignment(
        assignment_id="assignment",
        role="coder",
        model_id="model",
        provider_id="local",
        route=ForgeRoute.PATCH_DSL,
        method_variant=MethodVariant.EDIT_INTENT_LIST,
    )
    assert ModelOptimizationProfile.model_validate(profile.model_dump(mode="json")) == profile
    assert RoleAssignment.model_validate(assignment.model_dump(mode="json")) == assignment
    with pytest.raises(ValidationError):
        RoleAssignment.model_validate({**assignment.model_dump(), "unexpected": True})


def test_radar_unavailable_is_distinct_from_zero():
    score = CandidateScore(
        candidate_id="candidate",
        radar_scores={"speed": 0.0, "fallback_recovery": None},
        unavailable_dimensions=["fallback_recovery"],
    )
    assert score.radar_scores["speed"] == 0.0
    assert score.radar_scores["fallback_recovery"] is None
    assert "fallback_recovery" in score.unavailable_dimensions


def test_policy_enums_reject_unknown_values():
    with pytest.raises(ValidationError):
        ForgeExecutionRequest(
            request_id="request",
            stage=ForgeStage.PATCH_GENERATION,
            route_id=ForgeRoute.PATCH_DSL,
            task_decomposition_policy="file_size_policy",
        )
