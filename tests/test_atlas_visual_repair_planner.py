"""Unit tests for VisualRepairPlanner.

Two sets of tests:
1. universal_visual_repair — the default MVP profile; no restrictions, generic guidance.
2. Specialised profiles (animated_dom_repair, canvas_animation_repair, etc.) — still in the
   code for future opt-in use.  Tested by explicitly selecting the specialised contract via
   _plan_for_contract() instead of going through _reg.select() (which now always returns
   universal_visual_v1).
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
    """Plan using the default (universal) contract — what Atlas uses in production."""
    n = _norm.normalize(text)
    cls = _clf.classify(n, text)
    contract = _reg.select(cls)   # always universal_visual_v1 now
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


def _plan_for_contract(text: str, contract_id: str, failed_signals: list[str],
                       changed_files: list[str] | None = None) -> dict:
    """Plan using a specific (specialised) contract — for testing opt-in profiles."""
    n = _norm.normalize(text)
    cls = _clf.classify(n, text)
    contract = _reg.get(contract_id)
    assert contract is not None, f"Contract {contract_id} not found"
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
# universal_visual_repair — default MVP profile (no restrictions)
# ---------------------------------------------------------------------------

def test_universal_repair_never_mentions_collision_or_hud_as_instruction():
    plan = _plan_for("animate the text with rainbow colors", ["animation_signal"])
    assert plan["profile_id"] == "universal_visual_repair"
    instructions_text = "\n".join(i["action"] for i in plan["instructions"]).lower()
    assert "collision" not in instructions_text
    assert "hud state" not in instructions_text


def test_universal_repair_has_no_do_not_restrictions():
    plan = _plan_for("bounce the logo smoothly", ["animation_signal"])
    assert plan["do_not"] == [], "universal_visual_repair must have no do_not restrictions"


def test_universal_repair_mentions_animation_guidance():
    plan = _plan_for("make it animate", ["animation_signal"])
    full_text = _all_text(plan)
    assert "animation" in full_text or "keyframe" in full_text


def test_universal_repair_mentions_canvas_guidance():
    plan = _plan_for("canvas balls animation", ["canvas_exists"])
    full_text = _all_text(plan)
    assert "canvas" in full_text


def test_universal_repair_mentions_js_error_fix():
    plan = _plan_for("show a page", ["page_loads"])
    full_text = _all_text(plan)
    assert "error" in full_text or "js" in full_text or "load" in full_text


# ---------------------------------------------------------------------------
# Specialised profiles (opt-in via explicit contract_id) — still available
# ---------------------------------------------------------------------------

def test_animated_dom_repair_never_mentions_canvas():
    plan = _plan_for_contract(
        "animate the text with rainbow colors",
        "animated_dom_visual_v1",
        ["animation_signal", "style_change_over_time"],
    )
    text = _all_text(plan)
    assert any("canvas" in d for d in plan["do_not"]), "animated_dom do_not must forbid canvas"


def test_animated_dom_repair_never_mentions_collision():
    plan = _plan_for_contract(
        "bounce the logo smoothly",
        "animated_dom_visual_v1",
        ["animation_signal"],
    )
    instructions_text = "\n".join(i["action"] for i in plan["instructions"]).lower()
    assert "collision" not in instructions_text


def test_animated_dom_repair_never_mentions_hud():
    plan = _plan_for_contract(
        "pulse the header with a color fade",
        "animated_dom_visual_v1",
        ["color_change_detectable"],
    )
    instructions_text = "\n".join(i["action"] for i in plan["instructions"]).lower()
    assert "hud" not in instructions_text


def test_animated_dom_repair_never_mentions_game_loop():
    plan = _plan_for_contract(
        "hue-shift the background continuously",
        "animated_dom_visual_v1",
        ["animation_signal", "color_change_detectable"],
    )
    instructions_text = "\n".join(i["action"] for i in plan["instructions"]).lower()
    assert "game loop" not in instructions_text
    assert "game_loop" not in instructions_text


def test_animated_dom_repair_mentions_transform_opacity():
    plan = _plan_for_contract(
        "make the text animate smoothly",
        "animated_dom_visual_v1",
        ["animation_signal", "style_change_over_time"],
    )
    full_text = _all_text(plan)
    assert "transform" in full_text or "opacity" in full_text


def test_animated_dom_repair_mentions_reduced_motion():
    plan = _plan_for_contract(
        "continuously animate the background colors",
        "animated_dom_visual_v1",
        ["animation_signal"],
    )
    full_text = _all_text(plan)
    assert "reduced" in full_text or "prefers-reduced-motion" in full_text


# ---------------------------------------------------------------------------
# static_html_repair (opt-in specialised) — must NOT mention animation or game loop
# ---------------------------------------------------------------------------

def test_static_html_repair_never_mentions_animation():
    plan = _plan_for_contract(
        "make a simple static HTML page",
        "static_html_visual_v1",
        ["page_loads", "expected_structure"],
    )
    for instr in plan["instructions"]:
        act = instr["action"].lower()
        assert "add animation" not in act
        assert "add game" not in act
        assert "game loop" not in act


def test_static_html_repair_do_not_includes_animation():
    plan = _plan_for_contract(
        "static company page with information",
        "static_html_visual_v1",
        ["expected_structure"],
    )
    assert any("animation" in d.lower() for d in plan["do_not"])


def test_static_html_repair_do_not_includes_game_loop():
    plan = _plan_for_contract(
        "static page with product listing",
        "static_html_visual_v1",
        ["page_loads"],
    )
    assert any("game" in d.lower() for d in plan["do_not"])


# ---------------------------------------------------------------------------
# canvas_animation_repair (opt-in specialised) — canvas but no game state
# ---------------------------------------------------------------------------

def test_canvas_animation_repair_mentions_canvas_and_frame_loop():
    plan = _plan_for_contract(
        "canvas animation of bouncing circles",
        "canvas_animation_visual_v1",
        ["canvas_exists", "frame_changes_over_time"],
    )
    full_text = _all_text(plan)
    assert "canvas" in full_text
    assert "requestanimationframe" in full_text or "frame" in full_text


def test_canvas_animation_repair_forbids_game_mechanics():
    plan = _plan_for_contract(
        "canvas particle animation",
        "canvas_animation_visual_v1",
        ["canvas_exists"],
    )
    assert any("game" in d.lower() for d in plan["do_not"])
    assert any("score" in d.lower() or "lives" in d.lower() or "hud" in d.lower() for d in plan["do_not"])


# ---------------------------------------------------------------------------
# chart_repair (opt-in specialised) — must NOT mention animation or game
# ---------------------------------------------------------------------------

def test_chart_repair_never_mentions_game_loop():
    plan = _plan_for_contract(
        "bar chart showing sales data",
        "chart_visualization_v1",
        ["chart_element_exists", "data_points_visible"],
    )
    instructions_text = "\n".join(i["action"] for i in plan["instructions"]).lower()
    assert "game loop" not in instructions_text
    assert "collision" not in instructions_text


def test_chart_repair_mentions_data_and_axes():
    plan = _plan_for_contract(
        "pie chart for budget categories",
        "chart_visualization_v1",
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
