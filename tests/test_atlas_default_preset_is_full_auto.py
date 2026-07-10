"""Reproduces a real live-run bug: the DEFAULT preset used everywhere a run/safe-apply/
verification/clarification-revision request doesn't explicitly specify one was
"guarded_low_risk" (low-risk-only, approvals required), silently blocking any medium/high-risk
plan item with risk_not_allowed -- even though the app was configured for a fully autonomous
loop (only critical risk / delete / run_command should require a human).

"full_auto" already implements exactly that: allowed_risk_levels includes medium/high,
require_planitem_approval/require_patch_proposal_approval are False, while
AtlasAutomationGateService.decide_pre_safe_apply's critical_risk_not_allowed and
forbidden_action_type checks are unconditional (apply regardless of preset). So the fix is
just making full_auto the DEFAULT instead of guarded_low_risk -- these tests pin that default
everywhere it's read, so nobody can silently revert it back to a per-field literal.
"""
from agent.atlas_auto_policy_presets import (
    DEFAULT_AUTO_POLICY_PRESET_ID,
    atlas_auto_policy_presets,
)
from agent.atlas_auto_safe_apply_schema import AtlasAutoSafeApplyRequest
from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_run_orchestrator import AtlasRunOrchestratorRequest
from app.api.atlas_pipeline import AtlasAutoSafeApplyAndVerifyRequest
from app.api.atlas_runs import AtlasRunCreateRequest, AtlasRunStartRequest


def test_default_auto_policy_preset_id_is_full_auto():
    assert DEFAULT_AUTO_POLICY_PRESET_ID == "full_auto"
    assert DEFAULT_AUTO_POLICY_PRESET_ID in atlas_auto_policy_presets()


def test_run_and_safe_apply_request_defaults_use_full_auto():
    assert AtlasRunCreateRequest(pool_id="p").preset_id == "full_auto"
    assert AtlasRunStartRequest().preset_id == "full_auto"
    assert AtlasRunOrchestratorRequest(run_id="r", pool_id="p").preset_id == "full_auto"
    assert AtlasAutoSafeApplyAndVerifyRequest(pool_id="p", item_id="i").preset_id == "full_auto"
    assert AtlasAutoSafeApplyRequest(pool_id="p", item_id="i").preset_id == "full_auto"
    assert AtlasAutoVerificationRequest(pool_id="p", item_id="i").preset_id == "full_auto"


def test_full_auto_preset_allows_medium_and_high_risk_but_not_critical():
    # The exact behavior the default is meant to provide: everything except critical risk (and
    # delete/run_command, gated separately) proceeds without a human approval step.
    presets = atlas_auto_policy_presets()
    full_auto = presets["full_auto"]
    gate = AtlasAutomationGateService()

    def _item(risk_level: str):
        pool = AtlasPlanPool(pool_id="p1", root_goal="g", project_path="/tmp/repo")
        item = AtlasPlanItem(
            item_id="i1", pool_id="p1", title="t", goal="g", risk_level=risk_level,
            item_type="implementation", target_files=["a.py"],
            metadata={"action_type": "update", "proposed_content": "x = 1\n"},
        )
        return pool, item

    for risk in ("low", "medium", "high"):
        pool, item = _item(risk)
        decision = gate.decide_pre_safe_apply(pool, item, full_auto)
        assert decision.decision == "allow", (risk, decision.reasons)

    pool, item = _item("critical")
    decision = gate.decide_pre_safe_apply(pool, item, full_auto)
    assert decision.decision != "allow"
    assert "critical_risk_not_allowed" in decision.reasons


def test_guarded_low_risk_preset_still_exists_and_is_selectable():
    # The fix changes the DEFAULT, not the available options: an explicit, deliberate choice of
    # the stricter preset must still work exactly as before.
    presets = atlas_auto_policy_presets()
    assert "guarded_low_risk" in presets
    assert presets["guarded_low_risk"].allowed_risk_levels == ["low"]
