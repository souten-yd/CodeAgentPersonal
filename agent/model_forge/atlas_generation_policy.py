"""Atlas generation policy resolver for benchmark-aware Twin/Forge routing.

This module is the small, testable program that answers the runtime question:

* when a model has benchmark/profile evidence, should Atlas generation use the
  best safe route/method/Twin injection for that model?
* when optimal Forge routing is disabled, or the model is unbenchmarked, what is
  the safe fallback route/method/injection?

It intentionally does not mutate files, apply patches, or change production routing.
It only returns an ``ExecutionPolicy`` plus an audit summary that callers can attach to
Twin/Forge evidence before patch generation. RouteMatrix remains the safety authority:
benchmark fitness may only re-order safe candidates.
"""
from __future__ import annotations

import os
from typing import Mapping

from pydantic import Field

from agent.model_forge.capability_scoring import build_capability_profile
from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.route_fitness import derive_route_fitness
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel
from agent.twin_control_plane.contracts import ExecutionPolicy

ATLAS_FORGE_OPTIMAL_ROUTING_ENV = "ATLAS_FORGE_OPTIMAL_ROUTING"

_OFF_VALUES = {"0", "off", "false", "no", "disabled"}
_ON_VALUES = {"1", "on", "true", "yes", "enabled"}


class AtlasGenerationPolicyResolution(ForgeModel):
    """Auditable result for the policy Atlas should use for a generation attempt."""

    schema_version: str = FORGE_SCHEMA_VERSION
    provider_id: str = ""
    model_id: str = ""
    profile_available: bool = False
    optimal_routing_enabled: bool = True
    route_fitness_available: bool = False
    route_fitness_applied: bool = False
    selection_mode: str = ""  # benchmark_optimized | unbenchmarked_default | forge_optimal_routing_off | profile_without_route_fitness_default | benchmark_profile_kept_default
    policy: ExecutionPolicy
    route_fitness: dict[str, float] = Field(default_factory=dict)
    fallback_recommendation: dict[str, object] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


def resolve_forge_optimal_routing(value: str | None = None, *, env: Mapping[str, str] | None = None) -> bool:
    """Return whether benchmark/profile evidence may influence route selection.

    Defaults to ON to preserve the existing ExecutionPolicySelector behavior: when a
    persisted Forge profile has route fitness, it may re-order RouteMatrix's safe
    candidates. Set ``ATLAS_FORGE_OPTIMAL_ROUTING=0|off|false|no|disabled`` to keep the
    safe RouteMatrix default and still record that this was an explicit fallback.
    """
    source = os.environ if env is None else env
    raw = (value if value is not None else source.get(ATLAS_FORGE_OPTIMAL_ROUTING_ENV, "")).strip().lower()
    if not raw:
        return True
    if raw in _OFF_VALUES:
        return False
    if raw in _ON_VALUES:
        return True
    return True


def load_model_policy_inputs(
    *,
    model_id: str = "",
    provider_id: str = "",
    profile_store_dir: str | None = None,
) -> tuple[ModelCapabilityProfile, bool, dict[ForgeRoute, float]]:
    """Load the capability profile and benchmark route fitness for one model.

    Missing profile is neutral, not weak. Missing route fitness means the caller must keep
    the RouteMatrix default; no fabricated benchmark preference is produced.
    """
    if not model_id:
        return ModelCapabilityProfile(model_id="atlas-codegen", provider_id=provider_id), False, {}
    try:
        store = ProfileStore(profile_store_dir or "ca_data/model_forge/profiles")
        persisted = store.load_profile(provider_id, model_id)
        if persisted is None:
            return ModelCapabilityProfile(model_id=model_id, provider_id=provider_id), False, {}
        capability = build_capability_profile(persisted, model_id=model_id, provider_id=provider_id)
        return capability, True, derive_route_fitness(persisted.dimension_scores)
    except Exception:
        return ModelCapabilityProfile(model_id=model_id, provider_id=provider_id), False, {}


def resolve_atlas_generation_policy(
    *,
    change_class: ChangeClass | str = ChangeClass.MEDIUM,
    task_category: str = "autonomous_codegen",
    provider_id: str = "",
    model_id: str = "",
    profile_store_dir: str | None = None,
    optimal_routing: bool | None = None,
    capability_profile: ModelCapabilityProfile | None = None,
    profile_available: bool | None = None,
    route_preferences: dict[ForgeRoute, float] | None = None,
    consecutive_method_failures: int = 0,
) -> AtlasGenerationPolicyResolution:
    """Resolve the route/method/Twin injection policy for an Atlas generation attempt.

    ``capability_profile`` and ``route_preferences`` are optional injection points for tests
    and future callers that already loaded a profile. Production callers normally pass only
    provider/model/profile_store_dir.
    """
    if capability_profile is None or profile_available is None or route_preferences is None:
        loaded_profile, loaded_available, loaded_routes = load_model_policy_inputs(
            model_id=model_id, provider_id=provider_id, profile_store_dir=profile_store_dir,
        )
        if capability_profile is None:
            capability_profile = loaded_profile
        if profile_available is None:
            profile_available = loaded_available
        if route_preferences is None:
            route_preferences = loaded_routes

    enabled = resolve_forge_optimal_routing() if optimal_routing is None else bool(optimal_routing)
    effective_route_preferences = route_preferences if enabled else {}
    policy = ExecutionPolicySelector().select(
        ChangeClass(change_class),
        task_category=task_category,
        model_profile=capability_profile,
        route_preferences=effective_route_preferences or None,
        consecutive_method_failures=consecutive_method_failures,
    )

    route_fitness_available = bool(route_preferences)
    route_fitness_applied = any("benchmark_preferred_route" in reason for reason in policy.reasons)
    if not enabled:
        selection_mode = "forge_optimal_routing_off"
    elif not profile_available:
        selection_mode = "unbenchmarked_default"
    elif not route_fitness_available:
        selection_mode = "profile_without_route_fitness_default"
    elif route_fitness_applied:
        selection_mode = "benchmark_optimized"
    else:
        selection_mode = "benchmark_profile_kept_default"

    fallback_recommendation = {
        "route": policy.route.value,
        "method_variant": policy.method_variant.value if policy.method_variant else "",
        "method_fallbacks": [m.value for m in policy.method_fallbacks],
        "twin_injection_level": int(policy.twin_injection_level),
        "instruction_style": policy.instruction_style.value,
        "task_decomposition_policy": policy.task_decomposition_policy.value,
        "context_package_mode": policy.context_package_mode.value,
        "verification_mode": policy.verification_mode.value,
        "reason": selection_mode,
        "production_routing_changed": False,
    }

    reasons = [
        f"optimal_routing_enabled={enabled}",
        f"profile_available={bool(profile_available)}",
        f"route_fitness_available={route_fitness_available}",
        f"route_fitness_applied={route_fitness_applied}",
        f"selection_mode={selection_mode}",
        "RouteMatrix remains authority; benchmark fitness only reorders safe candidates.",
    ]
    reasons.extend(policy.reasons)

    return AtlasGenerationPolicyResolution(
        provider_id=provider_id or capability_profile.provider_id,
        model_id=model_id or capability_profile.model_id,
        profile_available=bool(profile_available),
        optimal_routing_enabled=enabled,
        route_fitness_available=route_fitness_available,
        route_fitness_applied=route_fitness_applied,
        selection_mode=selection_mode,
        policy=policy,
        route_fitness={route.value: score for route, score in (route_preferences or {}).items()},
        fallback_recommendation=fallback_recommendation,
        reasons=reasons,
    )


__all__ = [
    "ATLAS_FORGE_OPTIMAL_ROUTING_ENV",
    "AtlasGenerationPolicyResolution",
    "load_model_policy_inputs",
    "resolve_atlas_generation_policy",
    "resolve_forge_optimal_routing",
]
