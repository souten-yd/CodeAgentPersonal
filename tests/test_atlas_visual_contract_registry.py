"""Unit tests for VisualContractRegistry.

Covers contract selection correctness and — critically — negative tests verifying
that wrong contracts are never selected (e.g. canvas_game for a non-game task).
"""
from __future__ import annotations

import pytest

from agent.atlas_visual_requirement_normalizer import VisualRequirementNormalizer
from agent.atlas_visual_task_classifier import VisualTaskClassification, VisualTaskClassifier
from agent.atlas_visual_contract_registry import VisualContractRegistry, VisualContract

_norm = VisualRequirementNormalizer()
_clf = VisualTaskClassifier()
_reg = VisualContractRegistry()


def _contract_for(text: str) -> VisualContract:
    n = _norm.normalize(text)
    c = _clf.classify(n, text)
    return _reg.select(c)


def _make_classification(**kwargs) -> VisualTaskClassification:
    defaults = dict(
        artifact_type="unknown",
        visual_intent="unknown",
        interaction_intent="unknown",
        runtime_requirements=[],
        confidence=0.9,
        rationale="test",
    )
    defaults.update(kwargs)
    return VisualTaskClassification(**defaults)


# ---------------------------------------------------------------------------
# Contract selection — positive cases
# ---------------------------------------------------------------------------

def test_static_html_page_gets_static_contract():
    c = _contract_for("make a simple HTML page")
    assert c.contract_id == "static_html_visual_v1"


def test_animated_dom_page_gets_animated_dom_contract():
    c = _contract_for("animate the text with rainbow colors")
    assert c.contract_id == "animated_dom_visual_v1"


def test_ui_form_gets_ui_component_contract():
    c = _contract_for("form with name, email, and submit button")
    assert c.contract_id == "ui_component_visual_v1"


def test_canvas_animation_gets_canvas_animation_contract():
    c = _contract_for("canvas particle animation with requestAnimationFrame")
    assert c.contract_id == "canvas_animation_visual_v1"


def test_canvas_game_gets_canvas_game_contract():
    c = _contract_for("browser game with score, player, and collision on canvas")
    assert c.contract_id == "canvas_game_visual_v1"


def test_chart_gets_chart_contract():
    c = _contract_for("bar chart showing sales data by month")
    assert c.contract_id == "chart_visualization_v1"


# ---------------------------------------------------------------------------
# Critical negative tests — wrong contracts must never be selected
# ---------------------------------------------------------------------------

def test_animated_html_never_gets_canvas_game_contract():
    c = _contract_for("animate the header text with rainbow hue cycling")
    assert c.contract_id != "canvas_game_visual_v1"
    assert c.contract_id != "canvas_animation_visual_v1"


def test_static_html_never_gets_animation_contract():
    c = _contract_for("display a static company page with text and images")
    assert "animation_signal" not in c.required_signals
    assert c.contract_id == "static_html_visual_v1"


def test_canvas_animation_never_gets_canvas_game_contract():
    c = _contract_for("canvas animation of bouncing circles, no game mechanics")
    assert c.contract_id != "canvas_game_visual_v1"


def test_chart_never_gets_animation_contract():
    c = _contract_for("pie chart for budget categories")
    assert c.contract_id == "chart_visualization_v1"
    assert "animation_signal" not in c.required_signals
    assert "game_loop_runs" not in c.required_signals


def test_unknown_classification_falls_back_to_static_contract():
    unknown_cls = _make_classification(artifact_type="unknown", confidence=0.9)
    c = _reg.select(unknown_cls)
    assert c.contract_id == "static_html_visual_v1"


def test_low_confidence_falls_back_to_static_contract():
    low_cls = _make_classification(artifact_type="animated_html_page", confidence=0.3)
    c = _reg.select(low_cls)
    assert c.contract_id == "static_html_visual_v1"


def test_canvas_animation_without_canvas_required_demotes_to_animated_dom():
    cls = _make_classification(
        artifact_type="canvas_animation",
        runtime_requirements=[],  # no canvas_required flag
        confidence=0.85,
    )
    c = _reg.select(cls)
    # Must NOT select canvas_animation_visual_v1 when canvas_required is absent
    assert c.contract_id != "canvas_animation_visual_v1"
    assert c.contract_id == "animated_dom_visual_v1"


# ---------------------------------------------------------------------------
# Contract completeness
# ---------------------------------------------------------------------------

def test_all_contracts_have_required_signals():
    for cid in _reg.all_ids():
        c = _reg.get(cid)
        assert c is not None
        assert len(c.required_signals) > 0, f"{cid} has no required_signals"


def test_all_contracts_have_repair_profile():
    for cid in _reg.all_ids():
        c = _reg.get(cid)
        assert c.repair_profile, f"{cid} has no repair_profile"


def test_all_contracts_have_verification_method():
    for cid in _reg.all_ids():
        c = _reg.get(cid)
        assert c.verification_method in ("static_only", "smoke_optional", "smoke_required"), (
            f"{cid} has invalid verification_method: {c.verification_method}"
        )


def test_non_game_contracts_forbid_game_signals():
    non_game = [
        "static_html_visual_v1",
        "animated_dom_visual_v1",
        "ui_component_visual_v1",
        "chart_visualization_v1",
        "canvas_animation_visual_v1",
    ]
    for cid in non_game:
        c = _reg.get(cid)
        assert c is not None
        # game_loop_runs must be forbidden for non-game contracts
        assert "game_loop_runs" in c.forbidden_signals, (
            f"{cid} does not forbid game_loop_runs"
        )


def test_canvas_animation_forbids_hud_and_collision():
    c = _reg.get("canvas_animation_visual_v1")
    assert c is not None
    assert "hud_exists" in c.forbidden_signals
    assert "collision_detection" in c.forbidden_signals


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_selection_is_deterministic():
    text = "animate text with rainbow hue shifting"
    n = _norm.normalize(text)
    cls = _clf.classify(n, text)
    c1 = _reg.select(cls)
    c2 = _reg.select(cls)
    assert c1.contract_id == c2.contract_id


def test_get_returns_none_for_unknown_id():
    assert _reg.get("nonexistent_contract_id") is None


def test_get_returns_correct_contract():
    c = _reg.get("canvas_game_visual_v1")
    assert c is not None
    assert c.contract_id == "canvas_game_visual_v1"
