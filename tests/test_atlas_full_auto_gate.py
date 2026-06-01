from __future__ import annotations

from agent.atlas_autopilot_policy_schema import AtlasPolicyEvaluation
from agent.atlas_full_auto_gate import relax_evaluation_for_full_auto


def _eval(decision, categories, *, scope="item"):
    # Mirror how AtlasAutopilotPolicyGate builds evaluations: the boolean flags are always
    # kept consistent with the decision (see atlas_autopilot_policy.evaluate_item:116-118).
    return AtlasPolicyEvaluation(
        evaluation_id="ev_test",
        scope=scope,
        decision=decision,
        categories=list(categories),
        blocked=decision == "block",
        requires_user_confirmation=decision == "require_approval",
        auto_execution_allowed=decision == "allow",
    )


# ── Hard block is preserved even under full_auto ──────────────────────────────

def test_full_auto_keeps_block_on_critical_risk():
    out = relax_evaluation_for_full_auto(_eval("block", ["critical_risk"]), preset_id="full_auto")
    assert out.decision == "block"
    assert out.blocked is True


def test_full_auto_keeps_block_on_delete_and_run_command():
    for cat in ("delete_forbidden", "run_command_forbidden"):
        out = relax_evaluation_for_full_auto(_eval("block", [cat]), preset_id="full_auto")
        assert out.decision == "block", cat


def test_full_auto_keeps_block_on_terminal_status_manual_gate():
    # A failed/blocked item surfaces as a generic manual_gate block; it must NOT be resurrected.
    out = relax_evaluation_for_full_auto(_eval("block", ["manual_gate"]), preset_id="full_auto")
    assert out.decision == "block"


# ── Keep-approval categories stay gated ───────────────────────────────────────

def test_full_auto_keeps_approval_on_protected_path():
    out = relax_evaluation_for_full_auto(_eval("require_approval", ["protected_path"]), preset_id="full_auto")
    assert out.decision == "require_approval"
    assert out.requires_user_confirmation is True


# ── Quality-gate findings are relaxed to allow under full_auto ─────────────────

def test_full_auto_relaxes_require_approval_quality_categories():
    for cat in (
        "high_risk",
        "manual_gate",  # medium risk / requires_user_confirmation
        "dependency_change",
        "api_breaking_change",
        "ui_breaking_change",
        "docker_change",
        "database_migration",
        "security",
        "destructive_change",
        "too_many_files",
        "patch_too_large",
    ):
        out = relax_evaluation_for_full_auto(_eval("require_approval", [cat]), preset_id="full_auto")
        assert out.decision == "allow", cat
        assert out.auto_execution_allowed is True
        assert out.metadata.get("full_auto_relaxed") is True
        assert out.metadata.get("full_auto_original_decision") == "require_approval"


def test_full_auto_relaxes_data_loss_block_to_allow():
    # User opted into maximum autonomy; data_loss is reversible via the pre-apply snapshot.
    out = relax_evaluation_for_full_auto(_eval("block", ["data_loss"]), preset_id="full_auto")
    assert out.decision == "allow"
    assert out.blocked is False


def test_full_auto_keeps_block_when_data_loss_combined_with_hard_block():
    out = relax_evaluation_for_full_auto(_eval("block", ["data_loss", "critical_risk"]), preset_id="full_auto")
    assert out.decision == "block"


def test_full_auto_leaves_allow_untouched():
    src = _eval("allow", ["low_risk"])
    out = relax_evaluation_for_full_auto(src, preset_id="full_auto")
    assert out is src
    assert out.decision == "allow"


# ── Preset recognition (shared is_full_auto_preset) ───────────────────────────

def test_autonomous_presets_treated_as_full_auto():
    for preset in ("full_auto", "full_auto_multi_item_v1", "autonomous_bounded_dev", "autonomous_custom"):
        out = relax_evaluation_for_full_auto(_eval("require_approval", ["high_risk"]), preset_id=preset)
        assert out.decision == "allow", preset


def test_full_autopilot_automation_level_treated_as_full_auto():
    out = relax_evaluation_for_full_auto(_eval("require_approval", ["high_risk"]), automation_level="full_autopilot")
    assert out.decision == "allow"


# ── Non full_auto is unchanged (backward compatible) ──────────────────────────

def test_non_full_auto_preset_leaves_evaluation_unchanged():
    src = _eval("require_approval", ["high_risk"])
    out = relax_evaluation_for_full_auto(src, preset_id="guarded_low_risk")
    assert out is src
    assert out.decision == "require_approval"


def test_empty_preset_leaves_evaluation_unchanged():
    src = _eval("block", ["data_loss"])
    out = relax_evaluation_for_full_auto(src)
    assert out is src
    assert out.decision == "block"
