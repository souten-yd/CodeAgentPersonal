from __future__ import annotations
from agent.atlas_patch_regen_recommendation_schema import AtlasPatchRegenRecommendationPolicy


def list_patch_regen_recommendation_policies() -> list[AtlasPatchRegenRecommendationPolicy]:
    return [
        AtlasPatchRegenRecommendationPolicy(policy_id="patch_regen_recommendation_v1", name="Patch regen recommendation", description="Build recommendation payload only."),
        AtlasPatchRegenRecommendationPolicy(policy_id="patch_regen_recommendation_dry_run_v1", name="Patch regen recommendation dry run", description="Eligibility + preview only."),
        AtlasPatchRegenRecommendationPolicy(policy_id="strict_patch_regen_recommendation_v1", name="Strict patch regen recommendation", description="Strict deterministic recommendation policy.", eligible_retry_statuses=["not_retryable", "exhausted"], max_target_files=2),
    ]


def get_patch_regen_recommendation_policy(policy_id: str) -> AtlasPatchRegenRecommendationPolicy:
    for policy in list_patch_regen_recommendation_policies():
        if policy.policy_id == policy_id:
            return policy
    return list_patch_regen_recommendation_policies()[0]
