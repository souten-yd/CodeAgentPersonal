from __future__ import annotations

from agent.atlas_plan_quality_gate import apply_plan_quality_gate, is_full_auto_preset


def _plan(findings=None, consensus_risk="low", requires_revision=False, **extra):
    plan = {
        "requirement_summary": "build a small html animation",
        "goal": "animate a wave",
        "adversarial_critique": {
            "findings": findings or [],
            "consensus_risk": consensus_risk,
            "requires_revision": requires_revision,
        },
    }
    plan.update(extra)
    return plan


def _finding(severity="high", title="t", category="other", detail=""):
    return {"angle": "", "severity": severity, "category": category, "title": title, "detail": detail, "recommendation": ""}


# ── full_auto detection ───────────────────────────────────────────────────────

def test_full_auto_detected_from_preset():
    assert is_full_auto_preset(preset_id="autonomous_bounded_dev") is True
    assert is_full_auto_preset(preset_id="full_auto") is True
    assert is_full_auto_preset(automation_level="full_autopilot") is True


def test_non_full_auto_presets():
    assert is_full_auto_preset(preset_id="supervised_auto") is False
    assert is_full_auto_preset(preset_id="single_action") is False
    assert is_full_auto_preset(automation_level="plan_then_ask") is False


# ── No critique / clean ───────────────────────────────────────────────────────

def test_clean_plan_proceeds():
    out = apply_plan_quality_gate(_plan(), preset_id="supervised_auto")
    assert out["plan_revision_required"] is False
    assert out["require_approval"] is False


# ── Supervised preset: high critique blocks + plan_revision_required ──────────

def test_high_critique_supervised_blocks():
    out = apply_plan_quality_gate(
        _plan(findings=[_finding("high", "Lack of modularity", category="maintainability")]),
        preset_id="supervised_auto",
    )
    assert out["plan_revision_required"] is True
    assert out["require_approval"] is True
    assert out["critique_gate"]["gate_status"] == "blocked"
    assert "high_critique_requires_revision" in out["warnings"]


def test_requires_revision_supervised_blocks():
    out = apply_plan_quality_gate(_plan(requires_revision=True), preset_id="supervised_auto")
    assert out["plan_revision_required"] is True


# ── full_auto: non-safety high finding proceeds (recorded continuation) ───────

def test_full_auto_non_safety_high_finding_proceeds():
    out = apply_plan_quality_gate(
        _plan(findings=[_finding("high", "Lack of modularity", category="maintainability")],
              consensus_risk="high"),
        preset_id="autonomous_bounded_dev",
    )
    assert out["plan_revision_required"] is False
    assert out["require_approval"] is False
    assert out["critique_gate"]["gate_status"] == "full_auto_continued"
    assert out["critique_gate"]["reason"] == "full_auto_post_revision_continuation"
    assert out["critique_gate"]["residual_risk"] == "high"
    assert "full_auto_continued_with_unresolved_non_safety_critique" in out["warnings"]


def test_full_auto_blocks_empty_step_acceptance_before_continuation():
    out = apply_plan_quality_gate(
        _plan(
            findings=[_finding("high", "Lack of modularity", category="maintainability")],
            consensus_risk="high",
            implementation_steps=[{"title": "Create file", "description": "Create the requested file."}],
        ),
        preset_id="autonomous_bounded_dev",
    )
    assert out["plan_revision_required"] is True
    assert out["require_approval"] is True
    assert out["critique_gate"]["reason"] == "plan_structure_quality_gate_blocked"
    assert out["critique_gate"]["blocking_findings"][0]["code"] == "empty_step_acceptance_criteria"


# ── full_auto: safety-sensitive finding routed by critical_handling (default "ask") ───────

def _security_plan():
    return _plan(findings=[_finding("high", "auth logic not validated", category="security",
                                    detail="credential handling is unsafe")])


def test_full_auto_safety_sensitive_default_ask_pauses_for_approval():
    # New default critical_handling="ask": still gated (require_approval) but does NOT force a
    # re-plan; it pauses for a user decision.
    out = apply_plan_quality_gate(_security_plan(), preset_id="autonomous_bounded_dev")
    assert out["require_approval"] is True
    assert out["plan_revision_required"] is False
    assert out["critique_gate"]["safety_sensitive"] is True
    assert out["critique_gate"]["gate_status"] == "waiting_for_critical_decision"
    assert out["critique_gate"]["reason"] == "Critical event detected"


def test_full_auto_safety_sensitive_block_mode_still_waits_for_critical_decision():
    out = apply_plan_quality_gate(_security_plan(), preset_id="autonomous_bounded_dev", critical_handling="block")
    assert out["plan_revision_required"] is False
    assert out["require_approval"] is True
    assert out["critique_gate"]["gate_status"] == "waiting_for_critical_decision"
    assert out["critique_gate"]["safety_sensitive"] is True


def test_full_auto_safety_sensitive_auto_mode_still_waits_for_critical_decision():
    out = apply_plan_quality_gate(_security_plan(), preset_id="autonomous_bounded_dev", critical_handling="auto")
    assert out["plan_revision_required"] is False
    assert out["require_approval"] is True
    assert out["critique_gate"]["gate_status"] == "waiting_for_critical_decision"


def test_full_auto_critical_finding_treated_as_safety_sensitive():
    # critical severity is always safety-sensitive and now waits for explicit user judgment.
    out = apply_plan_quality_gate(
        _plan(findings=[_finding("critical", "missing core game loop", category="completeness")]),
        preset_id="autonomous_bounded_dev",
        critical_handling="block",
    )
    assert out["plan_revision_required"] is False
    assert out["critique_gate"]["gate_status"] == "waiting_for_critical_decision"
    # Default "ask" gates without forcing revision.
    out_ask = apply_plan_quality_gate(
        _plan(findings=[_finding("critical", "missing core game loop", category="completeness")]),
        preset_id="autonomous_bounded_dev",
    )
    assert out_ask["require_approval"] is True
    assert out_ask["plan_revision_required"] is False
