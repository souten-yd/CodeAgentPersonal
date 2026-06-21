"""Capability rescue policy: what to do when a model fails its construction methods.

If the benchmark shows a model cannot reliably produce ANY model-generated patch
(structured / patch-DSL / edit-intent / anchored all weak), we must not give up — we
rescue the work through a degraded-but-safe path. The rescue ladder, best to last:

1. ``none``                    — at least one construction method is viable; use the best.
2. ``deterministic_compile``   — the model can express edit intent well enough to compile
                                 deterministically into a Safe Apply patch.
3. ``deterministic_text_patch``— no model patch construction is trustworthy, but the change
                                 is mechanically expressible, so the system builds the patch.
4. ``escalate_fallback_model`` — a capable fallback model exists; reassign construction to it.
5. ``review_only``             — last resort: the model only analyses; a human applies.

Every rescue chain still ends in ``review_only`` and never bypasses Proposal / Safe Apply /
Verification. ``unavailable``/weak is never treated as competence.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent.model_forge.method_contracts import FallbackStep, MethodChain
from agent.model_forge.method_router import RECOVERABLE_TRIGGERS, CapabilityProfile
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.schema import ForgeModel
from agent.twin_control_plane.contracts import ModelCapabilityMode

_WEAK_THRESHOLD = 0.55

# Construction methods that depend on a model capability dimension to be trustworthy.
_METHOD_DIMENSION: dict[MethodVariant, str] = {
    MethodVariant.STRUCTURED_PATCH_JSON: "structured_output_fidelity",
    MethodVariant.PATCH_DSL_JSON: "patch_protocol_fidelity",
    MethodVariant.EDIT_INTENT_LIST: "edit_intent_quality",
    MethodVariant.ANCHORED_EDIT_BLOCK: "anchor_selection_quality",
}
# Preference order among model-generated construction methods.
_CONSTRUCTION_ORDER = [
    MethodVariant.STRUCTURED_PATCH_JSON,
    MethodVariant.PATCH_DSL_JSON,
    MethodVariant.EDIT_INTENT_LIST,
    MethodVariant.ANCHORED_EDIT_BLOCK,
]


class RescueLevel(StrEnum):
    NONE = "none"
    DETERMINISTIC_COMPILE = "deterministic_compile"
    DETERMINISTIC_TEXT_PATCH = "deterministic_text_patch"
    ESCALATE_FALLBACK_MODEL = "escalate_fallback_model"
    REVIEW_ONLY = "review_only"


class FallbackModelRef(ForgeModel):
    provider_id: str
    model_id: str
    # The fallback model's own capability scores, so we only escalate to a model that can
    # actually construct a patch.
    capability_scores: dict[str, float] = Field(default_factory=dict)


class RescuePlan(ForgeModel):
    rescue_level: RescueLevel
    primary_method: MethodVariant
    chain: MethodChain
    requires_human_review: bool = False
    escalate_to_provider: str = ""
    escalate_to_model: str = ""
    viable_methods: list[MethodVariant] = Field(default_factory=list)
    failing_dimensions: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _viable_methods(scores: dict[str, float], weaknesses: set[str]) -> list[MethodVariant]:
    viable: list[MethodVariant] = []
    for method in _CONSTRUCTION_ORDER:
        dim = _METHOD_DIMENSION[method]
        if dim in weaknesses:
            continue
        if dim not in scores:
            continue  # unmeasured is not competence
        if float(scores[dim]) >= _WEAK_THRESHOLD:
            viable.append(method)
    return viable


def _best_viable(scores: dict[str, float], viable: list[MethodVariant]) -> MethodVariant:
    return max(viable, key=lambda m: float(scores.get(_METHOD_DIMENSION[m], 0.0)))


def _chain(chain_id: str, primary: MethodVariant, fallbacks: list[MethodVariant]) -> MethodChain:
    seen: set[MethodVariant] = {primary}
    steps: list[FallbackStep] = []
    for variant in [*fallbacks, MethodVariant.REVIEW_ONLY]:
        if variant in seen:
            continue
        seen.add(variant)
        steps.append(FallbackStep(
            method_variant=variant,
            reason=f"rescue_fallback->{variant.value}",
            trigger_on=list(RECOVERABLE_TRIGGERS),
        ))
    return MethodChain(
        chain_id=chain_id,
        primary=primary,
        fallbacks=steps,
        stop_on=["passed"],
        hard_fail_on=["proposal_bypass", "safe_apply_bypass", "verification_bypass"],
    )


class CapabilityRescuePlanner:
    def plan(
        self,
        profile: CapabilityProfile,
        *,
        fallback_model: FallbackModelRef | None = None,
        deterministic_feasible: bool = True,
    ) -> RescuePlan:
        scores = dict(profile.capability_scores)
        weaknesses = set(profile.known_weaknesses)
        viable = _viable_methods(scores, weaknesses)
        failing = sorted(
            dim for method, dim in _METHOD_DIMENSION.items()
            if method not in viable
        )
        chain_id = f"rescue-{profile.model_id}"
        # Direct construction methods trusted to emit a full patch. Edit-intent is handled
        # separately because its safe path is a deterministic compile, not raw trust.
        viable_direct = [m for m in viable if m != MethodVariant.EDIT_INTENT_LIST]

        # 1. A direct construction method is viable — no rescue needed.
        if viable_direct and profile.mode != ModelCapabilityMode.AUDIT_ONLY:
            primary = _best_viable(scores, viable_direct)
            others = [m for m in viable if m != primary]
            return RescuePlan(
                rescue_level=RescueLevel.NONE,
                primary_method=primary,
                chain=_chain(chain_id, primary, others),
                viable_methods=viable,
                failing_dimensions=failing,
                reasons=[f"viable_construction_method:{primary.value}"],
            )

        # 2. Edit-intent is good enough for a deterministic compile into a Safe Apply patch.
        if MethodVariant.EDIT_INTENT_LIST in viable and profile.mode != ModelCapabilityMode.AUDIT_ONLY:
            return RescuePlan(
                rescue_level=RescueLevel.DETERMINISTIC_COMPILE,
                primary_method=MethodVariant.EDIT_INTENT_LIST,
                chain=_chain(chain_id, MethodVariant.EDIT_INTENT_LIST, [MethodVariant.DETERMINISTIC_TEXT_PATCH]),
                viable_methods=viable,
                failing_dimensions=failing,
                reasons=["edit_intent_viable_for_deterministic_compile"],
            )

        # 3. Escalate to a capable fallback model.
        if fallback_model is not None:
            fb_viable = _viable_methods(dict(fallback_model.capability_scores), set())
            if fb_viable:
                primary = _best_viable(dict(fallback_model.capability_scores), fb_viable)
                return RescuePlan(
                    rescue_level=RescueLevel.ESCALATE_FALLBACK_MODEL,
                    primary_method=primary,
                    chain=_chain(chain_id, primary, [m for m in fb_viable if m != primary]),
                    escalate_to_provider=fallback_model.provider_id,
                    escalate_to_model=fallback_model.model_id,
                    viable_methods=fb_viable,
                    failing_dimensions=failing,
                    reasons=[f"escalate_to_capable_fallback:{fallback_model.model_id}"],
                )

        # 4. No model can construct a patch, but the change is mechanically expressible.
        if deterministic_feasible and profile.mode != ModelCapabilityMode.AUDIT_ONLY:
            return RescuePlan(
                rescue_level=RescueLevel.DETERMINISTIC_TEXT_PATCH,
                primary_method=MethodVariant.DETERMINISTIC_TEXT_PATCH,
                chain=_chain(chain_id, MethodVariant.DETERMINISTIC_TEXT_PATCH, []),
                viable_methods=[],
                failing_dimensions=failing,
                reasons=["no_trustworthy_model_construction_uses_deterministic_text"],
            )

        # 5. Last resort: analysis only; a human applies. Still useful, never auto-applies.
        return RescuePlan(
            rescue_level=RescueLevel.REVIEW_ONLY,
            primary_method=MethodVariant.REVIEW_ONLY,
            chain=_chain(chain_id, MethodVariant.REVIEW_ONLY, []),
            requires_human_review=True,
            viable_methods=[],
            failing_dimensions=failing,
            reasons=["no_construction_path_degrade_to_review_only"],
        )


__all__ = ["RescueLevel", "FallbackModelRef", "RescuePlan", "CapabilityRescuePlanner"]
