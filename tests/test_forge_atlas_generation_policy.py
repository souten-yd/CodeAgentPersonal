from __future__ import annotations

from agent.model_forge.atlas_generation_policy import (
    resolve_atlas_generation_policy,
    resolve_forge_optimal_routing,
)
from agent.model_forge.execution_policy import ModelCapabilityProfile
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.twin_control_plane.contracts import ModelCapabilityMode


def test_optimal_routing_defaults_on_and_is_reversible():
    assert resolve_forge_optimal_routing(env={}) is True
    for value in ("0", "off", "false", "no", "disabled"):
        assert resolve_forge_optimal_routing(value) is False
    for value in ("1", "on", "true", "yes", "enabled"):
        assert resolve_forge_optimal_routing(value) is True


def test_unbenchmarked_model_gets_safe_default_policy():
    res = resolve_atlas_generation_policy(
        change_class=ChangeClass.MEDIUM,
        task_category="autonomous_codegen",
        model_id="unbenchmarked",
        provider_id="local",
        capability_profile=ModelCapabilityProfile(model_id="unbenchmarked", provider_id="local"),
        profile_available=False,
        route_preferences={},
        optimal_routing=True,
    )
    assert res.selection_mode == "unbenchmarked_default"
    assert res.profile_available is False
    assert res.route_fitness_applied is False
    # RouteMatrix default for medium changes remains the safe fallback.
    assert res.policy.route == ForgeRoute.PATCH_DSL
    assert res.policy.method_variant == MethodVariant.PATCH_DSL_JSON
    assert res.fallback_recommendation["production_routing_changed"] is False
    assert res.fallback_recommendation["route"] == "patch_dsl"


def test_benchmark_route_fitness_reorders_only_safe_candidates():
    profile = ModelCapabilityProfile(
        model_id="m1",
        provider_id="local",
        capability_scores={"structured_output_fidelity": 1.0, "patch_protocol_fidelity": 1.0},
        mode=ModelCapabilityMode.STANDARD,
    )
    res = resolve_atlas_generation_policy(
        change_class=ChangeClass.MEDIUM,
        task_category="autonomous_codegen",
        model_id="m1",
        provider_id="local",
        capability_profile=profile,
        profile_available=True,
        route_preferences={ForgeRoute.SLICED_IMPACT: 0.95, ForgeRoute.PATCH_DSL: 0.1},
        optimal_routing=True,
    )
    assert res.selection_mode == "benchmark_optimized"
    assert res.route_fitness_available is True
    assert res.route_fitness_applied is True
    assert res.policy.route == ForgeRoute.SLICED_IMPACT
    assert any("benchmark_preferred_route=sliced_impact" in r for r in res.policy.reasons)


def test_optimal_routing_off_ignores_benchmark_route_fitness():
    profile = ModelCapabilityProfile(model_id="m1", provider_id="local")
    res = resolve_atlas_generation_policy(
        change_class=ChangeClass.MEDIUM,
        task_category="autonomous_codegen",
        model_id="m1",
        provider_id="local",
        capability_profile=profile,
        profile_available=True,
        route_preferences={ForgeRoute.SLICED_IMPACT: 0.99, ForgeRoute.PATCH_DSL: 0.01},
        optimal_routing=False,
    )
    assert res.selection_mode == "forge_optimal_routing_off"
    assert res.optimal_routing_enabled is False
    assert res.route_fitness_available is True
    assert res.route_fitness_applied is False
    # OFF means keep RouteMatrix default for the change class.
    assert res.policy.route == ForgeRoute.PATCH_DSL
    assert not any("benchmark_preferred_route" in r for r in res.policy.reasons)


def test_critical_change_never_uses_benchmark_to_bypass_critical_gate():
    profile = ModelCapabilityProfile(model_id="m1", provider_id="local")
    res = resolve_atlas_generation_policy(
        change_class=ChangeClass.CRITICAL,
        task_category="autonomous_codegen",
        model_id="m1",
        provider_id="local",
        capability_profile=profile,
        profile_available=True,
        route_preferences={ForgeRoute.BLUEPRINT_SLICE: 1.0, ForgeRoute.CRITICAL_GATE: 0.0},
        optimal_routing=True,
    )
    assert res.policy.route == ForgeRoute.CRITICAL_GATE
    assert res.route_fitness_applied is False
    assert res.selection_mode == "benchmark_profile_kept_default"
    assert any("critical_change_routes_through_critical_gate" in r for r in res.policy.reasons)


def test_large_file_weak_profile_changes_method_and_injection_in_default_fallback():
    profile = ModelCapabilityProfile(
        model_id="weak",
        provider_id="local",
        capability_scores={"large_file_editing": 0.2},
        known_weaknesses=["large_file_editing"],
        mode=ModelCapabilityMode.WEAK_LOCAL,
    )
    res = resolve_atlas_generation_policy(
        change_class=ChangeClass.LARGE,
        task_category="autonomous_codegen",
        model_id="weak",
        provider_id="local",
        capability_profile=profile,
        profile_available=True,
        route_preferences={},
        optimal_routing=True,
    )
    assert res.selection_mode == "profile_without_route_fitness_default"
    # Even without benchmark route fitness, model capability still affects method and injection.
    assert res.policy.route == ForgeRoute.SLICED_IMPACT
    assert res.policy.method_variant == MethodVariant.ANCHORED_EDIT_BLOCK
    assert int(res.policy.twin_injection_level) >= 3
    assert "large_file_editing" in " ".join(res.policy.reasons)
