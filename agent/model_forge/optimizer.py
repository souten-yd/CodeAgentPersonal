"""Evidence-backed RoleAssignment and non-applying Loadout generation."""
from __future__ import annotations

from agent.model_forge.capability_scoring import build_capability_profile
from agent.model_forge.loadouts import Loadout
from agent.model_forge.method_router import MethodRouter
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ForgeModel, ModelOptimizationProfile, ModelProfile, RoleAssignment
from agent.model_forge.source_policy import SourceMode


class OptimizationResult(ForgeModel):
    status: str = "preview_not_applied"
    optimization_profile: ModelOptimizationProfile
    role_assignments: list[RoleAssignment]
    loadout: Loadout


class ForgeOptimizer:
    def optimize(self, profile: ModelProfile | None, *, provider_id: str, model_id: str) -> OptimizationResult:
        capability = build_capability_profile(profile, provider_id=provider_id, model_id=model_id)
        coder = MethodRouter().select(
            route=ForgeRoute.PATCH_DSL,
            change_class=ChangeClass.MEDIUM,
            profile=capability,
        )
        coder_assignment = RoleAssignment(
            assignment_id=f"role:{provider_id}:{model_id}:coder",
            role="coder",
            provider_id=provider_id,
            model_id=model_id,
            route=ForgeRoute.PATCH_DSL,
            method_variant=coder.chain.primary,
            fallback_methods=[step.method_variant for step in coder.chain.fallbacks],
            instruction_abstraction_level=coder.instruction_abstraction_level,
            confidence=self._confidence(profile),
            evidence_refs=list(profile.evidence_refs) if profile else [],
            reasons=list(coder.reasons),
        )
        reviewer_assignment = RoleAssignment(
            assignment_id=f"role:{provider_id}:{model_id}:reviewer",
            role="reviewer",
            provider_id=provider_id,
            model_id=model_id,
            route=ForgeRoute.CRITICAL_GATE,
            method_variant=MethodVariant.REVIEW_ONLY,
            fallback_methods=[],
            twin_injection_level=3,
            confidence=self._confidence(profile),
            evidence_refs=list(profile.evidence_refs) if profile else [],
            reasons=["review_role_never_constructs_patch"],
        )
        scores = capability.capability_scores
        optimization = ModelOptimizationProfile(
            profile_id=f"optimization:{provider_id}:{model_id}",
            provider_id=provider_id,
            model_id=model_id,
            method_fitness={
                MethodVariant.STRUCTURED_PATCH_JSON: scores.get("structured_output_fidelity", 0.5),
                MethodVariant.PATCH_DSL_JSON: scores.get("patch_protocol_fidelity", 0.5),
                MethodVariant.EDIT_INTENT_LIST: scores.get("edit_intent_quality", 0.5),
                MethodVariant.ANCHORED_EDIT_BLOCK: scores.get("anchor_selection_quality", 0.5),
            },
            preferred_methods=[coder.chain.primary],
            fallback_methods=[step.method_variant for step in coder.chain.fallbacks],
            instruction_abstraction_level=coder.instruction_abstraction_level,
            task_decomposition_policy=coder.task_decomposition_policy,
            context_package_mode=coder.context_package_mode,
            verification_mode=coder.verification_mode,
            evidence_refs=list(profile.evidence_refs) if profile else [],
        )
        assignments = [coder_assignment, reviewer_assignment]
        loadout = Loadout(
            loadout_id=f"optimized_{provider_id}_{model_id}".replace("/", "_"),
            display_name=f"Optimized {model_id}",
            description="Evidence-backed preview; save/apply requires existing Forge loadout flow.",
            source_mode=SourceMode.LOCAL_ONLY,
            provider_preferences=[provider_id],
            method_preferences={
                "coder": [coder.chain.primary],
                "reviewer": [MethodVariant.REVIEW_ONLY],
            },
            method_fallbacks={
                "coder": [step.method_variant for step in coder.chain.fallbacks],
                "reviewer": [],
            },
            role_assignments=assignments,
            risky=False,
        )
        return OptimizationResult(
            optimization_profile=optimization,
            role_assignments=assignments,
            loadout=loadout,
        )

    @staticmethod
    def _confidence(profile: ModelProfile | None) -> float:
        if profile is None or profile.sample_count <= 0:
            return 0.5
        return min(0.95, 0.5 + min(profile.sample_count, 9) * 0.05)
