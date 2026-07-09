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
            # Left unset this falls back to AtlasAutoPolicyPreset's schema default of 1, which blocks
            # nearly any real low-risk step (e.g. an HTML+CSS scaffold) with target_files_too_many
            # despite the preset otherwise gating on RISK, not file count. Every comparable cap in this
            # codebase (AtlasAutopilotPolicy's default, the various max_target_files policies) settles
            # on 5-10 as its baseline and 2 as the floor for an explicitly "strict" policy, so 1 here
            # reads as an omission rather than an intentional boundary. Match the general baseline (5)
            # — still well short of full_auto's 20, so guarded_low_risk stays meaningfully stricter.
            max_changed_files_per_item=5,
            allowed_action_types=["update", "create"],
            allowed_risk_levels=["low"],
        ),
        "full_auto": AtlasAutoPolicyPreset(
            preset_id="full_auto",
            name="Full Auto Code Generation",
            description="Autonomous create/update of low/medium/high-risk items (delete/run_command and critical risk still gated).",
            automation_level="guarded_low_risk",
            allow_auto_safe_apply=True,
            max_auto_items_per_run=20,
            max_changed_files_per_item=20,
            allowed_action_types=["update", "create"],
            allowed_risk_levels=["low", "medium", "high"],
            require_planitem_approval=False,
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
