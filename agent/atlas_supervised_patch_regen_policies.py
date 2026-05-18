from agent.atlas_supervised_patch_regen_schema import AtlasPatchRegenPolicy


POLICIES = {
    "supervised_patch_regen_v1": AtlasPatchRegenPolicy(
        policy_id="supervised_patch_regen_v1", name="Supervised Patch Regen v1", description="Generate patch candidate only with manual approval gate."
    ),
    "patch_regen_dry_run_v1": AtlasPatchRegenPolicy(
        policy_id="patch_regen_dry_run_v1", name="Patch Regen Dry Run v1", description="Dry run policy that never generates a patch.", allow_llm=False
    ),
    "strict_manual_patch_regen_v1": AtlasPatchRegenPolicy(
        policy_id="strict_manual_patch_regen_v1", name="Strict Manual Patch Regen v1", description="Stricter manual policy with smaller target-file scope.", max_target_files=2
    ),
}


def get_patch_regen_policy(policy_id: str) -> AtlasPatchRegenPolicy:
    return POLICIES.get(policy_id, POLICIES["supervised_patch_regen_v1"])


def list_patch_regen_policies() -> list[AtlasPatchRegenPolicy]:
    return list(POLICIES.values())
