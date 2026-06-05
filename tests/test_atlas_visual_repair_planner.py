"""Unit tests for VisualRepairPlanner.

Critical focus: negative tests prove non-game contracts NEVER produce
game/canvas repair guidance.
"""
from __future__ import annotations

import pytest

from agent.atlas_visual_contract_registry import VisualContractRegistry
from agent.atlas_visual_failure_taxonomy import VisualVerificationFailure, build_failure
from agent.atlas_visual_repair_planner import VisualRepairPlanner
from agent.atlas_visual_requirement_normalizer import VisualRequirementNormalizer
from agent.atlas_visual_task_classifier import VisualTaskClassification, VisualTaskClassifier

_norm = VisualRequirementNormalizer()
_clf = VisualTaskClassifier()
_reg = VisualContractRegistry()
_planner = VisualRepairPlanner()


def _plan_for(text: str, failed_signals: list[str], changed_files: list[str] | None = None) -> dict:
    n = _norm.normalize(text)
    cls = _clf.classify(n, text)
    contract = _reg.select(cls)
    failures = [
        build_failure(
            failure_type="visual_contract_failed",
            contract_id=contract.contract_id,
            failed_signal=sig,
            repair_profile=contract.repair_profile,
            failure_message_template=contract.failure_message_template,
        )
        for sig in failed_signals
    ]
    return _planner.plan_repair(
        failures=failures,
        classification=cls,
        contract=contract,
        diagnostics={},
        changed_files=changed_files or ["index.html", "main.js"],
    ).to_dict()


def _all_text(plan: dict) -> str:
    """Flatten all text in a plan dict for negative assertions."""
    parts = [plan.get("profile_id", ""), plan.get("display_name", "")]
    for instr in plan.get("instructions") or []:
        parts.append(instr.get("action", ""))
        parts.append(instr.get("rationale", ""))
    for item in plan.get("do_not") or []:
        parts.append(item)
    for rf in plan.get("rationale_per_failure") or []:
        parts.append(rf.get("instruction", ""))
        parts.append(rf.get("rationale", ""))
    return "\n".join(parts).lower()


# ---------------------------------------------------------------------------
# animated_dom_repair — must NOT mention game/canvas/HUD concepts
# ---------------------------------------------------------------------------

def test_animated_dom_repair_never_mentions_canvas():
    plan = _plan_for(
        "animate the text with rainbow colors",
        ["animation_signal", "style_change_over_time"],
    )
    text = _all_text(plan)
    # do_not list must explicitly forbid canvas
    assert any("canvas" in d for d in plan["do_not"]), "do_not must forbid canvas"
    # instructions must not suggest adding canvas
    for instr in plan["instructions"]:
        assert "canvas" not in instr["action"].lower() or "do not" in instr["action"].lower()


def test_animated_dom_repair_never_mentions_collision():
    plan = _plan_for(
        "bounce the logo smoothly",
        ["animation_signal"],
    )
    # Negative: collision must not appear in do_not list or instructions as something to ADD
    instructions_text = "\n".join(i["action"] for i in plan["instructions"]).lower()
    # "collision" should only appear in do_not, not as a positive instruction
    assert "collision" not in instructions_text


def test_animated_dom_repair_never_mentions_hud():
    plan = _plan_for(
        "pulse the header with a color fade",
        ["color_change_detectable"],
    )
    # HUD must not appear anywhere as something to add
    instructions_text = "\n".join(i["action"] for i in plan["instructions"]).lower()
    assert "hud" not in instructions_text


def test_animated_dom_repair_never_mentions_game_loop():
    plan = _plan_for(
        "hue-shift the background continuously",
        ["animation_signal", "color_change_detectable"],
    )
    instructions_text = "\n".join(i["action"] for i in plan["instructions"]).lower()
    assert "game loop" not in instructions_text
    assert "game_loop" not in instructions_text


def test_animated_dom_repair_mentions_transform_opacity():
    plan = _plan_for(
        "make the text animate smoothly",
        ["animation_signal", "style_change_over_time"],
    )
    # Should suggest using transform/opacity
    full_text = _all_text(plan)
    assert "transform" in full_text or "opacity" in full_text


def test_animated_dom_repair_mentions_reduced_motion():
    plan = _plan_for(
        "continuously animate the background colors",
        ["animation_signal"],
    )
    full_text = _all_text(plan)
    assert "reduced" in full_text or "prefers-reduced-motion" in full_text


# ---------------------------------------------------------------------------
# static_html_repair — must NOT mention animation or game loop
# ---------------------------------------------------------------------------

def test_static_html_repair_never_mentions_animation():
    plan = _plan_for(
        "make a simple static HTML page",
        ["page_loads", "expected_structure"],
    )
    full_text = _all_text(plan)
    # "add animation" should NOT appear as a positive instruction
    for instr in plan["instructions"]:
        act = instr["action"].lower()
        assert "add animation" not in act
        assert "add game" not in act
        assert "game loop" not in act


def test_static_html_repair_do_not_includes_animation():
    plan = _plan_for(
        "static company page with information",
        ["expected_structure"],
    )
    assert any("animation" in d.lower() for d in plan["do_not"])


def test_static_html_repair_do_not_includes_game_loop():
    plan = _plan_for(
        "static page with product listing",
        ["page_loads"],
    )
    assert any("game" in d.lower() for d in plan["do_not"])


# ---------------------------------------------------------------------------
# canvas_animation_repair — canvas but no game state
# ---------------------------------------------------------------------------

def test_canvas_animation_repair_mentions_canvas_and_frame_loop():
    plan = _plan_for(
        "canvas animation of bouncing circles",
        ["canvas_exists", "frame_changes_over_time"],
    )
    full_text = _all_text(plan)
    assert "canvas" in full_text
    assert "requestanimationframe" in full_text or "frame" in full_text


def test_canvas_animation_repair_forbids_game_mechanics():
    plan = _plan_for(
        "canvas particle animation",
        ["canvas_exists"],
    )
    assert any("game" in d.lower() for d in plan["do_not"])
    assert any("score" in d.lower() or "lives" in d.lower() or "hud" in d.lower() for d in plan["do_not"])


# ---------------------------------------------------------------------------
# chart_repair — must NOT mention animation or game
# ---------------------------------------------------------------------------

def test_chart_repair_never_mentions_game_loop():
    plan = _plan_for(
        "bar chart showing sales data",
        ["chart_element_exists", "data_points_visible"],
    )
    instructions_text = "\n".join(i["action"] for i in plan["instructions"]).lower()
    assert "game loop" not in instructions_text
    assert "collision" not in instructions_text


def test_chart_repair_mentions_data_and_axes():
    plan = _plan_for(
        "pie chart for budget categories",
        ["data_points_visible"],
    )
    full_text = _all_text(plan)
    assert "data" in full_text


# ---------------------------------------------------------------------------
# Repair plan structure
# ---------------------------------------------------------------------------

def test_repair_plan_includes_rationale_per_failure():
    plan = _plan_for(
        "animate rainbow text",
        ["animation_signal", "color_change_detectable"],
    )
    assert len(plan["rationale_per_failure"]) == 2
    for rf in plan["rationale_per_failure"]:
        assert "failed_signal" in rf
        assert "instruction" in rf
        assert "rationale" in rf


def test_repair_plan_target_files_bounded_to_changed_files():
    changed = ["src/index.html", "src/main.js", "src/style.css"]
    plan = _plan_for(
        "animate the header text",
        ["animation_signal"],
        changed_files=changed,
    )
    for f in plan["target_files"]:
        assert f in changed


def test_repair_plan_max_retries_positive():
    plan = _plan_for(
        "make a bouncing ball animation",
        ["animation_signal"],
    )
    assert plan["max_retries"] >= 1


def test_repair_plan_auto_repair_allowed_for_safe_profiles():
    plan = _plan_for(
        "animate the text fading in",
        ["animation_signal"],
    )
    assert plan["auto_repair_allowed"] is True


def test_repair_plan_unknown_profile_falls_back_safely():
    from agent.atlas_visual_contract_registry import VisualContract
    bad_contract = VisualContract(
        contract_id="fake_contract_v1",
        display_name="Fake",
        required_signals=["animation_signal"],
        optional_signals=[],
        forbidden_signals=[],
        verification_method="smoke_optional",
        repair_profile="nonexistent_repair_profile",
        failure_message_template="",
    )
    cls = VisualTaskClassification(
        artifact_type="animated_html_page",
        visual_intent="element_animation",
        interaction_intent="none",
        runtime_requirements=["animation_required"],
        confidence=0.8,
        rationale="test",
    )
    failures = [
        build_failure(
            failure_type="visual_contract_failed",
            contract_id="fake_contract_v1",
            failed_signal="animation_signal",
            repair_profile="nonexistent_repair_profile",
        )
    ]
    plan = _planner.plan_repair(failures, cls, bad_contract, {}, ["index.html"]).to_dict()
    # Should fall back to static_html_repair without raising
    assert plan["profile_id"] == "static_html_repair"
    assert any("no repair profile" in w.lower() for w in plan["warnings"])
