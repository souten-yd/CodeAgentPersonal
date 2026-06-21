"""Forge Execution Policy Matrix MVP.

This layer sits above RouteMatrix. RouteMatrix still decides the route; this
module chooses model capability mode, Twin injection level, instruction style,
required gates, and Git policy for that route/model/task combination.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1

from agent.model_forge.capability_rescue import (
    CapabilityRescuePlanner,
    FallbackModelRef,
    RescueLevel,
)
from agent.model_forge.method_policy import PatchConstructionMode
from agent.model_forge.route_matrix import ChangeClass, RouteMatrix, RouteSelector
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.method_router import MethodRouter
from agent.model_forge.method_taxonomy import MethodVariant
from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    GitPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinInjectionLevel,
    default_hard_constraints,
)


@dataclass(frozen=True)
class ModelCapabilityProfile:
    model_id: str
    provider_id: str = ""
    capability_scores: dict[str, float] = field(default_factory=dict)
    known_weaknesses: list[str] = field(default_factory=list)
    mode: ModelCapabilityMode = ModelCapabilityMode.STANDARD
    recommended_twin_assist_mode: str = ""
    recommended_twin_injection_level: int | None = None
    twin_assist_lift: dict[str, float] = field(default_factory=dict)
    slot_quality_accepted: bool | None = None

    def score(self, dimension: str, default: float = 0.5) -> float:
        value = self.capability_scores.get(dimension, default)
        return max(0.0, min(1.0, float(value)))


_ROUTE_INJECTION_RANGE: dict[ForgeRoute, tuple[int, int]] = {
    ForgeRoute.DETERMINISTIC: (0, 1),
    ForgeRoute.MICRO_PATCH: (0, 2),
    ForgeRoute.DIRECT_PATCH: (1, 3),
    ForgeRoute.PATCH_DSL: (1, 3),
    ForgeRoute.TEST_FIRST: (2, 4),
    ForgeRoute.REPAIR_LOOP: (2, 4),
    ForgeRoute.SLICED_IMPACT: (2, 4),
    ForgeRoute.BLUEPRINT_SLICE: (2, 4),
    ForgeRoute.CRITICAL_GATE: (3, 4),
    ForgeRoute.GREENFIELD_SKELETON: (3, 4),
    ForgeRoute.PORTAL_REPLAY_REPAIR: (2, 4),
}


def _clamp_injection(route: ForgeRoute, level: int) -> TwinInjectionLevel:
    low, high = _ROUTE_INJECTION_RANGE.get(route, (1, 3))
    return TwinInjectionLevel(max(low, min(high, int(level))))


def _policy_id(parts: list[str]) -> str:
    return "execpol_" + sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def _style_for_route(route: ForgeRoute, mode: ModelCapabilityMode, weaknesses: set[str]) -> InstructionStyle:
    if mode == ModelCapabilityMode.AUDIT_ONLY:
        return InstructionStyle.AUDIT_ONLY
    if route == ForgeRoute.TEST_FIRST:
        return InstructionStyle.ASSUMPTION_BREAKER if "stale_test_judgment" in weaknesses else InstructionStyle.TEST_FIRST
    if route in {ForgeRoute.REPAIR_LOOP, ForgeRoute.PORTAL_REPLAY_REPAIR}:
        return InstructionStyle.REPAIR_COMPASS
    if route in {ForgeRoute.BLUEPRINT_SLICE, ForgeRoute.GREENFIELD_SKELETON}:
        return InstructionStyle.BLUEPRINT_SLICE if mode == ModelCapabilityMode.FRONTIER_ASSISTED else InstructionStyle.INTERFACE_FIRST
    if route == ForgeRoute.PATCH_DSL:
        return InstructionStyle.PATCH_DSL
    if mode == ModelCapabilityMode.FRONTIER_ASSISTED:
        return InstructionStyle.FREEFORM_DESIGN
    return InstructionStyle.CONSTRAINED_PATCH


def _base_injection(profile: ModelCapabilityProfile, *, task_category: str, change_class: ChangeClass) -> int:
    if profile.mode == ModelCapabilityMode.AUDIT_ONLY:
        return 1
    if profile.mode == ModelCapabilityMode.FRONTIER_ASSISTED:
        base = 1
    elif profile.mode == ModelCapabilityMode.WEAK_LOCAL:
        base = 3
    else:
        base = 2

    weak_dims = 0
    for dim in ("impact_analysis", "contract_preservation", "test_generation", "stale_test_judgment", "flag_reasoning"):
        if profile.score(dim) < 0.55:
            weak_dims += 1
    if weak_dims >= 3:
        base += 1
    if task_category in {"repair", "failure", "bugfix", "portal_repair"}:
        base += 1
    if change_class in {ChangeClass.LARGE, ChangeClass.CRITICAL, ChangeClass.GREENFIELD}:
        base += 1
    return base


class ExecutionPolicySelector:
    """Select a complete execution policy without taking over route selection."""

    def __init__(
        self,
        route_selector: RouteSelector | None = None,
        method_router: MethodRouter | None = None,
    ) -> None:
        self._route_selector = route_selector or RouteSelector(RouteMatrix())
        self._method_router = method_router or MethodRouter()

    def select(
        self,
        change_class: ChangeClass | str,
        *,
        task_category: str = "",
        requested_route: ForgeRoute | str | None = None,
        model_profile: ModelCapabilityProfile | None = None,
        route_preferences: dict | None = None,
        twin_risk: str = "medium",
        consecutive_method_failures: int = 0,
        rescue_fallback_model: FallbackModelRef | None = None,
    ) -> ExecutionPolicy:
        change = ChangeClass(change_class)
        profile = model_profile or ModelCapabilityProfile(model_id="default")
        route_selection = self._route_selector.select(change, task_category=task_category, requested_route=requested_route)
        # Benchmark x injection: among the RouteMatrix's SAFE candidates, prefer the route
        # the model performs best at (route_preferences). RouteMatrix stays the authority —
        # we only re-order within the safe set, never override safety or a critical gate.
        benchmark_route = None
        if (route_preferences and requested_route is None
                and not route_selection.critical_gate_required
                and route_selection.candidates_considered):
            from agent.model_forge.route_fitness import best_route
            benchmark_route = best_route(route_selection.candidates_considered, route_preferences)
            if benchmark_route is not None and benchmark_route != route_selection.selected_route:
                route_selection = self._route_selector.select(
                    change, task_category=task_category, requested_route=benchmark_route)
        route = route_selection.selected_route
        method_decision = self._method_router.select(
            route=route,
            change_class=change,
            profile=profile,
            consecutive_failures=consecutive_method_failures,
        )
        # Method selection from the router.
        method_primary = method_decision.chain.primary
        method_fallbacks = [step.method_variant for step in method_decision.chain.fallbacks]
        patch_construction_mode = method_decision.patch_construction_mode
        rescue_reason = ""
        # Capability rescue: only when all four construction dimensions are measured and
        # all fail. Partial/unmeasured profiles defer to the router defaults (no override).
        _CONSTRUCTION_DIMS = {
            "structured_output_fidelity", "patch_protocol_fidelity",
            "edit_intent_quality", "anchor_selection_quality",
        }
        if _CONSTRUCTION_DIMS <= set(profile.capability_scores):
            rescue = CapabilityRescuePlanner().plan(profile, fallback_model=rescue_fallback_model)
            if rescue.rescue_level in {
                RescueLevel.DETERMINISTIC_TEXT_PATCH,
                RescueLevel.REVIEW_ONLY,
                RescueLevel.ESCALATE_FALLBACK_MODEL,
            }:
                method_primary = rescue.primary_method
                method_fallbacks = [step.method_variant for step in rescue.chain.fallbacks]
                rescue_reason = f"capability_rescue={rescue.rescue_level.value}"
                if rescue.rescue_level == RescueLevel.REVIEW_ONLY:
                    patch_construction_mode = PatchConstructionMode.NONE
                elif rescue.rescue_level == RescueLevel.DETERMINISTIC_TEXT_PATCH:
                    patch_construction_mode = PatchConstructionMode.DETERMINISTIC_TEXT
                if rescue.escalate_to_model:
                    rescue_reason += f":to={rescue.escalate_to_provider}:{rescue.escalate_to_model}"
        weaknesses = set(profile.known_weaknesses)
        base_level = _base_injection(profile, task_category=task_category, change_class=change)
        if twin_risk == "high":
            base_level += 1
        elif twin_risk == "low":
            base_level -= 1
        injection = _clamp_injection(route, base_level)
        if profile.recommended_twin_injection_level is not None:
            injection = _clamp_injection(route, max(int(injection), profile.recommended_twin_injection_level))
        style = _style_for_route(route, profile.mode, weaknesses)

        required_modules = ["TwinBrief"]
        if injection >= TwinInjectionLevel.CONTRACTS_AND_IMPACT:
            required_modules.extend(["BlastMap", "ContractSentinel"])
        if injection >= TwinInjectionLevel.CONSTRAINED_WITH_TESTS:
            required_modules.append("TwinProof")
        if injection >= TwinInjectionLevel.STRICT_INTERFACE_AND_REPAIR:
            required_modules.append("RepairCompass")

        gates = ["SafeApplyBoundary", "RemotePublishApprovalGate"]
        if injection >= TwinInjectionLevel.CONTRACTS_AND_IMPACT:
            gates.append("ContractSentinel")
        if injection >= TwinInjectionLevel.CONSTRAINED_WITH_TESTS:
            gates.extend(["TwinProof", "NoTestWeakening"])
        if change in {ChangeClass.LARGE, ChangeClass.CRITICAL, ChangeClass.GREENFIELD}:
            gates.append("PatchImpactGate")
        if "flag_reasoning" in weaknesses or profile.score("flag_reasoning") < 0.55:
            gates.append("FeatureFlagBaseline")

        reasons = [*route_selection.reasons]
        reasons.append(f"model_mode={profile.mode}")
        reasons.append(f"twin_risk={twin_risk}")
        reasons.append(f"injection={int(injection)}")
        if profile.recommended_twin_assist_mode:
            reasons.append(f"twin_assist_recommendation={profile.recommended_twin_assist_mode}")
        if benchmark_route is not None:
            reasons.append(f"benchmark_preferred_route={benchmark_route.value}:{round(route_preferences.get(benchmark_route, 0), 3)}")
        if weaknesses:
            reasons.append("known_weaknesses=" + ",".join(sorted(weaknesses)))
        reasons.extend(method_decision.reasons)
        if rescue_reason:
            reasons.append(rescue_reason)

        return ExecutionPolicy(
            policy_id=_policy_id([
                str(change), task_category, str(route), profile.model_id, str(injection), style.value,
                method_primary.value,
            ]),
            route=route,
            model_id=profile.model_id,
            model_role="reviewer" if profile.mode == ModelCapabilityMode.AUDIT_ONLY else "coder",
            instruction_style=style,
            model_capability_mode=profile.mode,
            method_variant=method_primary,
            method_fallbacks=method_fallbacks,
            instruction_abstraction_level=method_decision.instruction_abstraction_level,
            task_decomposition_policy=method_decision.task_decomposition_policy,
            context_package_mode=method_decision.context_package_mode,
            output_protocol=method_decision.output_protocol,
            patch_construction_mode=patch_construction_mode,
            verification_mode=method_decision.verification_mode,
            repair_mode=method_decision.repair_mode,
            twin_injection_level=injection,
            twin_assist_mode=profile.recommended_twin_assist_mode,
            twin_assist_expected_lift=(max(profile.twin_assist_lift.values()) if profile.twin_assist_lift else None),
            twin_slot_required=profile.recommended_twin_assist_mode == "twin_localized_slot",
            deterministic_anchor_required=profile.recommended_twin_assist_mode == "twin_deterministic_anchor",
            avoid_method_variants=([MethodVariant.EDIT_INTENT_LIST] if profile.score("edit_intent_quality") < 0.55 else []),
            required_twin_modules=sorted(set(required_modules)),
            required_gates=sorted(set(gates)),
            git_policy=GitPolicy(
                local_branch_required=change != ChangeClass.TRIVIAL,
                worktree_preferred=change in {ChangeClass.LARGE, ChangeClass.CRITICAL, ChangeClass.GREENFIELD},
                local_commit_required=change != ChangeClass.TRIVIAL,
                remote_publication_requires_approval=True,
                remote_mutation_requires_approval=True,
            ),
            hard_constraints=default_hard_constraints(),
            advisory_context=[f"route_candidates={','.join(map(str, route_selection.candidates_considered))}"],
            reasons=reasons,
            confidence=0.8 if not route_selection.overridden else 0.7,
        )


__all__ = ["ExecutionPolicySelector", "ModelCapabilityProfile"]
