from __future__ import annotations

from agent.atlas_auto_policy_schema import AtlasAutoPolicyPreset


def atlas_auto_policy_presets() -> dict[str, AtlasAutoPolicyPreset]:
    return {
        "manual_only": AtlasAutoPolicyPreset(
            preset_id="manual_only",
            name="Manual Only",
            description="Decision-only mode: always require manual action.",
            automation_level="manual_only",
        ),
        "guarded_low_risk": AtlasAutoPolicyPreset(
            preset_id="guarded_low_risk",
            name="Guarded Low Risk",
            description="Allows only gated low-risk create/update readiness decisions.",
            automation_level="guarded_low_risk",
            allow_auto_safe_apply=True,
            max_auto_items_per_run=1,
            allowed_action_types=["update", "create"],
            allowed_risk_levels=["low"],
        ),
        "full_auto": AtlasAutoPolicyPreset(
            preset_id="full_auto",
            name="Full Auto Safe Apply",
            description="Allows gated create/update safe_apply for low, medium, and high risk items while keeping critical and command actions forbidden.",
            automation_level="full_autopilot",
            allow_auto_safe_apply=True,
            max_auto_items_per_run=3,
            max_changed_files_per_item=20,
            allowed_action_types=["update", "create"],
            allowed_risk_levels=["low", "medium", "high"],
            require_patch_proposal_approval=False,
        ),
        "supervised_auto": AtlasAutoPolicyPreset(
            preset_id="supervised_auto",
            name="Supervised Auto (Reserved)",
            description="Reserved for future supervised automation flows.",
            automation_level="supervised_auto",
            notes=["Defined only in PR-37; execution is not enabled."],
        ),
    }
