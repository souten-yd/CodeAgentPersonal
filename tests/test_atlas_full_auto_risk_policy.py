"""10th: full-automation code generation must apply medium/high-risk create/update items (a real
program needs them), while the guarded preset still restricts to low risk. The automation gate must
respect the preset's allowed_risk_levels instead of hardcoding a low-only ceiling."""
from __future__ import annotations

from types import SimpleNamespace

from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_multi_item_autopilot_policies import get_multi_item_policy


def _item(risk):
    return SimpleNamespace(
        item_id="i1", risk_level=risk, item_type="implementation", status="ready",
        target_files=["game.js"],
        metadata={"action_type": "create", "approval": {"decision": "approved"}, "proposed_content": "x"},
    )


def _pool():
    return SimpleNamespace(pool_id="p1", project_path="/tmp/proj")


def _decide(risk, preset_id):
    gate = AtlasAutomationGateService()
    preset = atlas_auto_policy_presets()[preset_id]
    return gate.decide_pre_safe_apply(_pool(), _item(risk), preset).decision


def test_full_auto_preset_allows_medium_and_high():
    assert _decide("low", "full_auto") == "allow"
    assert _decide("medium", "full_auto") == "allow"
    assert _decide("high", "full_auto") == "allow"


def test_full_auto_preset_still_blocks_critical():
    assert _decide("critical", "full_auto") == "block"


def test_guarded_preset_still_blocks_medium_high():
    # medium/high are a hard block under the guarded preset; low is not blocked (it may still be
    # require_manual due to approval bookkeeping, but it is never a risk block).
    assert _decide("low", "guarded_low_risk") != "block"
    assert _decide("medium", "guarded_low_risk") == "block"
    assert _decide("high", "guarded_low_risk") == "block"


def test_full_auto_policy_allows_higher_risk_levels():
    p = get_multi_item_policy("full_auto_multi_item_v1")
    assert set(p.allowed_risk_levels) == {"low", "medium", "high"}
    assert p.require_approval is False
    # Guarded policy unchanged.
    assert get_multi_item_policy("guarded_multi_item_v1").allowed_risk_levels == ["low"]


def test_panel_uses_full_auto_policy():
    import pathlib
    js = pathlib.Path("web/js/atlas_claude_panel.js").read_text(encoding="utf-8")
    assert "full_auto_multi_item_v1" in js
    assert "policy_id: 'guarded_multi_item_v1'" not in js
