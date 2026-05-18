from __future__ import annotations

from agent.atlas_patch_regen_from_recommendation_schema import AtlasPatchRegenFromRecommendationPolicy


POLICIES = {
    "patch_regen_from_recommendation_v1": AtlasPatchRegenFromRecommendationPolicy(
        policy_id="patch_regen_from_recommendation_v1",
        name="Patch Regen From Recommendation v1",
        description="Manually execute supervised patch candidate generation from a saved recommendation payload.",
    ),
    "patch_regen_from_recommendation_dry_run_v1": AtlasPatchRegenFromRecommendationPolicy(
        policy_id="patch_regen_from_recommendation_dry_run_v1",
        name="Patch Regen From Recommendation Dry Run v1",
        description="Validate saved recommendation payload only; never call supervised patch regeneration.",
        allow_patch_regen_execution=False,
    ),
    "strict_patch_regen_from_recommendation_v1": AtlasPatchRegenFromRecommendationPolicy(
        policy_id="strict_patch_regen_from_recommendation_v1",
        name="Strict Patch Regen From Recommendation v1",
        description="Strict validation for manual recommendation-triggered patch regeneration.",
        max_target_files=2,
        max_original_patch_chars=24000,
        notes=["Blocks recommendations that already contain warnings."],
    ),
}


def get_patch_regen_from_recommendation_policy(policy_id: str) -> AtlasPatchRegenFromRecommendationPolicy:
    return POLICIES.get(policy_id, POLICIES["patch_regen_from_recommendation_v1"])


def list_patch_regen_from_recommendation_policies() -> list[AtlasPatchRegenFromRecommendationPolicy]:
    return list(POLICIES.values())
