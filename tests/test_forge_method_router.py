from __future__ import annotations

from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
from agent.model_forge.method_policy import (
    InstructionAbstractionLevel,
    PatchConstructionMode,
    TaskDecompositionPolicy,
)
from agent.model_forge.method_router import MethodRouter
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_matrix import ChangeClass, RouteMatrix, RouteSelector
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.contracts import ModelCapabilityMode


def test_structured_output_weak_model_uses_edit_intents():
    profile = ModelCapabilityProfile(
        model_id="weak-structured",
        mode=ModelCapabilityMode.WEAK_LOCAL,
        capability_scores={"structured_output_fidelity": 0.3},
    )
    decision = MethodRouter().select(
        route=ForgeRoute.PATCH_DSL,
        change_class=ChangeClass.MEDIUM,
        profile=profile,
    )
    assert decision.chain.primary == MethodVariant.EDIT_INTENT_LIST
    assert decision.chain.fallbacks[0].method_variant == MethodVariant.ANCHORED_EDIT_BLOCK
    assert decision.instruction_abstraction_level == InstructionAbstractionLevel.EXPLICIT_TEMPLATE
    assert decision.task_decomposition_policy == TaskDecompositionPolicy.MICRO_PATCH_ONLY


def test_large_editing_weakness_prefers_anchored_method():
    profile = ModelCapabilityProfile(
        model_id="weak-large",
        capability_scores={"large_file_editing": 0.2},
    )
    decision = MethodRouter().select(
        route=ForgeRoute.SLICED_IMPACT,
        change_class=ChangeClass.LARGE,
        profile=profile,
    )
    assert decision.chain.primary == MethodVariant.ANCHORED_EDIT_BLOCK
    assert decision.chain.fallbacks[0].method_variant == MethodVariant.UNIFIED_DIFF


def test_repeated_failure_degrades_to_review_only():
    profile = ModelCapabilityProfile(model_id="repeated")
    decision = MethodRouter().select(
        route=ForgeRoute.DIRECT_PATCH,
        change_class=ChangeClass.SMALL,
        profile=profile,
        consecutive_failures=2,
    )
    assert decision.chain.primary == MethodVariant.REVIEW_ONLY
    assert decision.patch_construction_mode == PatchConstructionMode.NONE
    assert decision.chain.fallbacks == []


def test_missing_new_dimensions_do_not_make_legacy_profile_weak():
    profile = ModelCapabilityProfile(model_id="legacy", capability_scores={"impact_analysis": 0.8})
    decision = MethodRouter().select(
        route=ForgeRoute.PATCH_DSL,
        change_class=ChangeClass.MEDIUM,
        profile=profile,
    )
    assert decision.chain.primary == MethodVariant.PATCH_DSL_JSON


def test_execution_policy_attaches_method_without_overriding_route_matrix():
    route_selector = RouteSelector(RouteMatrix())
    expected = route_selector.select(ChangeClass.LARGE, requested_route=ForgeRoute.MICRO_PATCH)
    profile = ModelCapabilityProfile(
        model_id="weak-large",
        capability_scores={"large_file_editing": 0.2},
    )
    policy = ExecutionPolicySelector(route_selector=route_selector).select(
        ChangeClass.LARGE,
        requested_route=ForgeRoute.MICRO_PATCH,
        model_profile=profile,
    )
    assert policy.route == expected.selected_route
    assert policy.route != ForgeRoute.MICRO_PATCH
    assert policy.method_variant == MethodVariant.ANCHORED_EDIT_BLOCK
    assert MethodVariant.UNIFIED_DIFF in policy.method_fallbacks


def test_critical_route_is_preserved_when_repeated_failures_select_review():
    policy = ExecutionPolicySelector().select(
        ChangeClass.CRITICAL,
        model_profile=ModelCapabilityProfile(model_id="review"),
        consecutive_method_failures=3,
    )
    assert policy.route == ForgeRoute.CRITICAL_GATE
    assert policy.method_variant == MethodVariant.REVIEW_ONLY
    assert policy.patch_construction_mode == PatchConstructionMode.NONE
