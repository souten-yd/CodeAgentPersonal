"""Profile-aware Method selection that never owns or overrides Forge routes."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

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

if TYPE_CHECKING:
    # Imported lazily inside ``select`` at runtime to break the
    # contracts <-> model_forge import cycle (contracts imports method_policy,
    # which eagerly loads this module). See repo note on order-dependent ImportError.
    from agent.twin_control_plane.contracts import ModelCapabilityMode


class CapabilityProfile(Protocol):
    model_id: str
    capability_scores: dict[str, float]
    known_weaknesses: list[str]
    mode: ModelCapabilityMode
    recommended_twin_assist_mode: str
    slot_quality_accepted: bool | None


# PR18: the real failure vocabulary the structured/edit/anchored adapters actually
# emit. The original chains only triggered on a subset (schema_invalid /
# missing_edit_anchor / anchor_not_found), so a weak model failing with
# content_missing / file_changes_missing would never fall back. Fallback steps now
# trigger on the full recoverable set.
RECOVERABLE_TRIGGERS: list[str] = [
    "schema_invalid",
    "content_missing",
    "file_changes_missing",
    "missing_edit_anchor",
    "invalid_edit_intent",
    "anchor_not_found",
    "empty_output",
    "unsafe_target_path",
    "forbidden_action_type",
    "failed",
    "blocked",
]

_STRONG_THRESHOLD = 0.7
_WEAK_THRESHOLD = 0.55


class MethodRoutingDecision(ForgeModel):
    chain: MethodChain
    instruction_abstraction_level: InstructionAbstractionLevel
    task_decomposition_policy: TaskDecompositionPolicy
    context_package_mode: ContextPackageMode
    output_protocol: OutputProtocol
    patch_construction_mode: PatchConstructionMode
    verification_mode: VerificationMode
    repair_mode: RepairMode
    # PR18: refinement signals derived from measured capability strengths/weaknesses.
    verifier_separation: bool = False
    lower_injection: bool = False
    deterministic_compile: bool = False
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
        from agent.twin_control_plane.contracts import ModelCapabilityMode

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
            recommendation = str(getattr(profile, "recommended_twin_assist_mode", "") or "")
            slot_allowed = getattr(profile, "slot_quality_accepted", None) is not False
            if recommendation == "twin_localized_slot" and slot_allowed:
                primary = MethodVariant.TWIN_LOCALIZED_SLOT_PATCH
                reasons = ["measured_large_edit_weakness_uses_recommended_twin_slot"]
            elif recommendation == "twin_deterministic_anchor" and slot_allowed:
                primary = MethodVariant.TWIN_DETERMINISTIC_ANCHOR_PATCH
                reasons = ["measured_large_edit_weakness_uses_recommended_twin_anchor"]
            else:
                primary = MethodVariant.ANCHORED_EDIT_BLOCK
                reasons = ["slot_quality_blocked_uses_anchors" if recommendation and not slot_allowed else "large_editing_weakness_uses_anchors"]
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

        abstraction = (
            InstructionAbstractionLevel.EXPLICIT_TEMPLATE if weak_mode
            else InstructionAbstractionLevel.CONCRETE_STEPS
        )
        decomposition = (
            TaskDecompositionPolicy.MICRO_PATCH_ONLY if weak_mode
            else TaskDecompositionPolicy.NARROW_SLICE
        )
        context_mode = ContextPackageMode.IMPACT_SLICE if weak_mode else ContextPackageMode.TWIN_BRIEF
        verification = (
            VerificationMode.FULL_GATE if review_mode or change_class == ChangeClass.CRITICAL
            else VerificationMode.AFFECTED_TESTS
        )
        repair = RepairMode.HUMAN_REVIEW if review_mode else RepairMode.FALLBACK_METHOD
        patch_mode = self._patch_mode(primary)
        verifier_separation = False
        lower_injection = False
        deterministic_compile = False

        # ---- PR18 v2 refinements (measured strengths/weaknesses only; never for review) ----
        if not review_mode:
            if self._weak(profile, "abstraction_tolerance"):
                very_weak = self._score(profile, "abstraction_tolerance") < 0.4
                abstraction = (
                    InstructionAbstractionLevel.YES_NO_GATE if very_weak
                    else InstructionAbstractionLevel.FILL_IN_TEMPLATE
                )
                reasons.append("abstraction_weakness_uses_template")
            if self._weak(profile, "context_overload_sensitivity"):
                context_mode = ContextPackageMode.MINIMAL
                reasons.append("context_overload_uses_minimal_refs")
            if self._strong(profile, "test_generation"):
                decomposition = TaskDecompositionPolicy.TEST_FIRST_SLICE
                verification = (
                    VerificationMode.FULL_GATE if change_class == ChangeClass.CRITICAL
                    else VerificationMode.FOCUSED_TESTS
                )
                reasons.append("test_generation_strength_uses_test_first")
            if self._strong(profile, "repair_discipline"):
                repair = RepairMode.REPAIR_COMPASS
                reasons.append("repair_strength_uses_repair_loop")
            if self._weak(profile, "evidence_discipline"):
                verifier_separation = True
                verification = VerificationMode.FULL_GATE
                reasons.append("evidence_weakness_separates_verifier")
            if self._weak(profile, "structured_output_fidelity") and self._strong(profile, "edit_intent_quality"):
                deterministic_compile = True
                patch_mode = PatchConstructionMode.DETERMINISTIC_TEXT
                reasons.append("structured_weak_edit_strong_uses_deterministic_compile")
            if profile.mode == ModelCapabilityMode.FRONTIER_ASSISTED:
                lower_injection = True
                abstraction = InstructionAbstractionLevel.GUIDED_GOAL
                decomposition = TaskDecompositionPolicy.LIGHT
                context_mode = ContextPackageMode.TWIN_BRIEF
                reasons.append("frontier_assisted_lowers_injection")

        return MethodRoutingDecision(
            chain=chain,
            instruction_abstraction_level=abstraction,
            task_decomposition_policy=decomposition,
            context_package_mode=context_mode,
            output_protocol=self._output_protocol(primary),
            patch_construction_mode=patch_mode,
            verification_mode=verification,
            repair_mode=repair,
            verifier_separation=verifier_separation,
            lower_injection=lower_injection,
            deterministic_compile=deterministic_compile,
            reasons=reasons,
        )

    @staticmethod
    def _measured(profile: CapabilityProfile, dimension: str) -> bool:
        return dimension in profile.capability_scores

    def _strong(self, profile: CapabilityProfile, dimension: str) -> bool:
        return self._measured(profile, dimension) and float(
            profile.capability_scores[dimension]
        ) >= _STRONG_THRESHOLD

    def _weak(self, profile: CapabilityProfile, dimension: str) -> bool:
        if dimension in profile.known_weaknesses:
            return True
        return self._measured(profile, dimension) and float(
            profile.capability_scores[dimension]
        ) < _WEAK_THRESHOLD

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
        # PR18: every fallback triggers on the full recoverable failure vocabulary so a
        # real weak model that fails with content_missing / file_changes_missing (not just
        # schema_invalid) still degrades. A review-only terminal guarantees recovery.
        if primary in {MethodVariant.STRUCTURED_PATCH_JSON, MethodVariant.PATCH_DSL_JSON}:
            return [
                FallbackStep(
                    method_variant=MethodVariant.EDIT_INTENT_LIST,
                    reason="structured output recovery",
                    trigger_on=list(RECOVERABLE_TRIGGERS),
                ),
                FallbackStep(
                    method_variant=MethodVariant.ANCHORED_EDIT_BLOCK,
                    reason="edit intent recovery",
                    trigger_on=list(RECOVERABLE_TRIGGERS),
                ),
                FallbackStep(
                    method_variant=MethodVariant.REVIEW_ONLY,
                    reason="degrade to review when no method applies",
                    trigger_on=list(RECOVERABLE_TRIGGERS),
                ),
            ]
        if primary == MethodVariant.EDIT_INTENT_LIST:
            return [
                FallbackStep(
                    method_variant=MethodVariant.ANCHORED_EDIT_BLOCK,
                    reason="edit intent recovery",
                    trigger_on=list(RECOVERABLE_TRIGGERS),
                ),
                FallbackStep(
                    method_variant=MethodVariant.REVIEW_ONLY,
                    reason="degrade to review when no method applies",
                    trigger_on=list(RECOVERABLE_TRIGGERS),
                ),
            ]
        if primary == MethodVariant.ANCHORED_EDIT_BLOCK:
            return [
                FallbackStep(
                    method_variant=MethodVariant.UNIFIED_DIFF,
                    reason="anchor recovery",
                    trigger_on=list(RECOVERABLE_TRIGGERS),
                ),
                FallbackStep(
                    method_variant=MethodVariant.REVIEW_ONLY,
                    reason="degrade to review when no method applies",
                    trigger_on=list(RECOVERABLE_TRIGGERS),
                ),
            ]
        if primary in {MethodVariant.TWIN_LOCALIZED_SLOT_PATCH, MethodVariant.TWIN_DETERMINISTIC_ANCHOR_PATCH}:
            return [
                FallbackStep(method_variant=MethodVariant.REVIEW_ONLY, reason="unsafe or unavailable Twin slot", trigger_on=list(RECOVERABLE_TRIGGERS)),
            ]
        if primary == MethodVariant.REPAIR_COMPASS_STEPS:
            return [FallbackStep(
                method_variant=MethodVariant.REVIEW_ONLY,
                reason="repair analysis recovery",
                trigger_on=list(RECOVERABLE_TRIGGERS),
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
