"""Profile-aware Method selection that never owns or overrides Forge routes."""
from __future__ import annotations

from typing import Protocol

from pydantic import Field

from agent.model_forge.method_contracts import FallbackStep, MethodChain
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
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ForgeModel
from agent.twin_control_plane.contracts import ModelCapabilityMode


class CapabilityProfile(Protocol):
    model_id: str
    capability_scores: dict[str, float]
    known_weaknesses: list[str]
    mode: ModelCapabilityMode


class MethodRoutingDecision(ForgeModel):
    chain: MethodChain
    instruction_abstraction_level: InstructionAbstractionLevel
    task_decomposition_policy: TaskDecompositionPolicy
    context_package_mode: ContextPackageMode
    output_protocol: OutputProtocol
    patch_construction_mode: PatchConstructionMode
    verification_mode: VerificationMode
    repair_mode: RepairMode
    reasons: list[str] = Field(default_factory=list)


class MethodRouter:
    def select(
        self,
        *,
        route: ForgeRoute,
        change_class: ChangeClass,
        profile: CapabilityProfile,
        consecutive_failures: int = 0,
    ) -> MethodRoutingDecision:
        weaknesses = set(profile.known_weaknesses)
        structured_weak = (
            "structured_output_fidelity" in weaknesses
            or self._score(profile, "structured_output_fidelity") < 0.55
            or self._score(profile, "patch_protocol_fidelity") < 0.55
        )
        large_edit_weak = (
            change_class in {ChangeClass.LARGE, ChangeClass.CRITICAL, ChangeClass.GREENFIELD}
            and (
                "large_file_editing" in weaknesses
                or self._score(profile, "large_file_editing") < 0.55
            )
        )

        if consecutive_failures >= 2 or profile.mode == ModelCapabilityMode.AUDIT_ONLY:
            primary = MethodVariant.REVIEW_ONLY
            reasons = ["repeated_failure_review_only" if consecutive_failures >= 2 else "audit_only_profile"]
        elif large_edit_weak:
            primary = MethodVariant.ANCHORED_EDIT_BLOCK
            reasons = ["large_editing_weakness_uses_anchors"]
        elif structured_weak:
            primary = MethodVariant.EDIT_INTENT_LIST
            reasons = ["structured_output_weakness_uses_edit_intents"]
        else:
            primary = self._default_for_route(route)
            reasons = [f"route_default_method={route.value}:{primary.value}"]

        chain = MethodChain(
            chain_id=f"method-{profile.model_id}-{route.value}",
            primary=primary,
            fallbacks=self._fallbacks_for(primary),
            hard_fail_on=["proposal_bypass", "safe_apply_bypass", "verification_bypass"],
        )
        weak_mode = profile.mode == ModelCapabilityMode.WEAK_LOCAL or structured_weak or large_edit_weak
        review_mode = primary == MethodVariant.REVIEW_ONLY
        return MethodRoutingDecision(
            chain=chain,
            instruction_abstraction_level=(
                InstructionAbstractionLevel.EXPLICIT_TEMPLATE if weak_mode
                else InstructionAbstractionLevel.CONCRETE_STEPS
            ),
            task_decomposition_policy=(
                TaskDecompositionPolicy.MICRO_PATCH_ONLY if weak_mode
                else TaskDecompositionPolicy.NARROW_SLICE
            ),
            context_package_mode=(
                ContextPackageMode.IMPACT_SLICE if weak_mode
                else ContextPackageMode.TWIN_BRIEF
            ),
            output_protocol=self._output_protocol(primary),
            patch_construction_mode=self._patch_mode(primary),
            verification_mode=(
                VerificationMode.FULL_GATE if review_mode or change_class == ChangeClass.CRITICAL
                else VerificationMode.AFFECTED_TESTS
            ),
            repair_mode=(RepairMode.HUMAN_REVIEW if review_mode else RepairMode.FALLBACK_METHOD),
            reasons=reasons,
        )

    @staticmethod
    def _score(profile: CapabilityProfile, dimension: str) -> float:
        return float(profile.capability_scores.get(dimension, 0.7))

    @staticmethod
    def _default_for_route(route: ForgeRoute) -> MethodVariant:
        if route == ForgeRoute.DETERMINISTIC:
            return MethodVariant.DETERMINISTIC_TEXT_PATCH
        if route == ForgeRoute.PATCH_DSL:
            return MethodVariant.PATCH_DSL_JSON
        if route in {ForgeRoute.REPAIR_LOOP, ForgeRoute.PORTAL_REPLAY_REPAIR}:
            return MethodVariant.REPAIR_COMPASS_STEPS
        return MethodVariant.STRUCTURED_PATCH_JSON

    @staticmethod
    def _fallbacks_for(primary: MethodVariant) -> list[FallbackStep]:
        if primary in {MethodVariant.STRUCTURED_PATCH_JSON, MethodVariant.PATCH_DSL_JSON}:
            return [FallbackStep(
                method_variant=MethodVariant.EDIT_INTENT_LIST,
                reason="structured output recovery",
                trigger_on=["schema_invalid"],
            )]
        if primary == MethodVariant.EDIT_INTENT_LIST:
            return [FallbackStep(
                method_variant=MethodVariant.ANCHORED_EDIT_BLOCK,
                reason="edit intent recovery",
                trigger_on=["schema_invalid", "missing_edit_anchor"],
            )]
        if primary == MethodVariant.ANCHORED_EDIT_BLOCK:
            return [FallbackStep(
                method_variant=MethodVariant.UNIFIED_DIFF,
                reason="anchor recovery",
                trigger_on=["anchor_not_found"],
            )]
        if primary == MethodVariant.REPAIR_COMPASS_STEPS:
            return [FallbackStep(
                method_variant=MethodVariant.REVIEW_ONLY,
                reason="repair analysis recovery",
                trigger_on=["schema_invalid"],
            )]
        return []

    @staticmethod
    def _output_protocol(method: MethodVariant) -> OutputProtocol:
        return {
            MethodVariant.PATCH_DSL_JSON: OutputProtocol.PATCH_DSL_JSON,
            MethodVariant.EDIT_INTENT_LIST: OutputProtocol.EDIT_INTENT_LIST,
            MethodVariant.ANCHORED_EDIT_BLOCK: OutputProtocol.ANCHORED_EDIT_BLOCK,
            MethodVariant.UNIFIED_DIFF: OutputProtocol.UNIFIED_DIFF,
            MethodVariant.REVIEW_ONLY: OutputProtocol.FREEFORM_TEXT,
            MethodVariant.REPAIR_COMPASS_STEPS: OutputProtocol.STRUCTURED_JSON,
        }.get(method, OutputProtocol.STRUCTURED_JSON)

    @staticmethod
    def _patch_mode(method: MethodVariant) -> PatchConstructionMode:
        if method == MethodVariant.DETERMINISTIC_TEXT_PATCH:
            return PatchConstructionMode.DETERMINISTIC_TEXT
        if method in {MethodVariant.REVIEW_ONLY, MethodVariant.REPAIR_COMPASS_STEPS}:
            return PatchConstructionMode.NONE
        return PatchConstructionMode.MODEL_GENERATED
