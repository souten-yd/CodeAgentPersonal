"""Unit tests for VisualTaskClassifier.

Covers positive classification and — critically — negative tests that verify
game/canvas concepts are NOT injected into non-game visual tasks.
"""
from __future__ import annotations

import pytest

from agent.atlas_visual_requirement_normalizer import VisualRequirementNormalizer
from agent.atlas_visual_task_classifier import VisualTaskClassifier, VisualTaskClassification

_norm = VisualRequirementNormalizer()
_clf = VisualTaskClassifier()


def _classify(text: str) -> VisualTaskClassification:
    return _clf.classify(_norm.normalize(text), text)


# ---------------------------------------------------------------------------
# Static HTML page
# ---------------------------------------------------------------------------

def test_static_html_page_classified_correctly():
    c = _classify("create a simple static HTML page displaying company information")
    assert c.artifact_type == "static_html_page"
    assert c.visual_intent == "static_render"
    assert c.interaction_intent == "none"


def test_static_html_no_animation_requirements():
    c = _classify("a static HTML page with company information")
    assert "animation_required" not in c.runtime_requirements
    assert "canvas_required" not in c.runtime_requirements
    assert "runtime_loop_required" not in c.runtime_requirements
    assert "input_required" not in c.runtime_requirements


def test_static_html_no_game_concepts():
    c = _classify("make a simple landing page")
    # Negative: no game concepts injected
    assert c.artifact_type != "canvas_game"
    assert "canvas_required" not in c.runtime_requirements


# ---------------------------------------------------------------------------
# Animated DOM page
# ---------------------------------------------------------------------------

def test_animated_dom_rainbow_text_classified_correctly():
    c = _classify("animate the text with rainbow colors cycling through the spectrum")
    assert c.artifact_type == "animated_html_page"
    assert c.visual_intent in ("text_animation", "element_animation")
    assert "animation_required" in c.runtime_requirements


def test_animated_dom_no_canvas_requirement():
    c = _classify("make the header text pulse with rainbow colors")
    assert "canvas_required" not in c.runtime_requirements
    assert c.artifact_type != "canvas_animation"
    assert c.artifact_type != "canvas_game"


def test_animated_dom_bounce_classified_correctly():
    c = _classify("make the logo bounce up and down smoothly")
    assert c.artifact_type == "animated_html_page"
    assert "animation_required" in c.runtime_requirements
    assert "canvas_required" not in c.runtime_requirements


def test_animated_dom_no_game_loop_no_hud():
    c = _classify("fade in text over 2 seconds")
    # Critical negative test: no game-related signals
    assert "game_loop_runs" not in c.runtime_requirements
    assert c.artifact_type != "canvas_game"
    assert c.interaction_intent != "game_controls"


# ---------------------------------------------------------------------------
# UI component
# ---------------------------------------------------------------------------

def test_form_ui_classified_correctly():
    c = _classify("build a form with name, email, and a submit button with validation")
    assert c.artifact_type == "ui_component"
    assert c.visual_intent == "form_input"
    assert c.interaction_intent == "form_submit"


def test_ui_component_no_game_loop():
    c = _classify("create a modal dialog with a close button")
    assert "game_loop_runs" not in c.runtime_requirements
    assert "canvas_required" not in c.runtime_requirements
    assert c.artifact_type not in ("canvas_game", "canvas_animation")


# ---------------------------------------------------------------------------
# Canvas animation (no game)
# ---------------------------------------------------------------------------

def test_canvas_animation_classified_correctly():
    c = _classify("canvas animation of bouncing balls using requestAnimationFrame")
    assert c.artifact_type == "canvas_animation"
    assert c.visual_intent == "canvas_motion"
    assert "canvas_required" in c.runtime_requirements
    assert "runtime_loop_required" in c.runtime_requirements


def test_canvas_animation_no_game_state():
    c = _classify("particle system animation on a canvas, no game mechanics")
    assert c.artifact_type == "canvas_animation"
    # Negative: no game-specific requirements injected
    assert c.interaction_intent != "game_controls"


# ---------------------------------------------------------------------------
# Canvas game
# ---------------------------------------------------------------------------

def test_canvas_game_classified_correctly():
    c = _classify("browser game with score counter, player character, and collision detection on canvas")
    assert c.artifact_type == "canvas_game"
    assert c.visual_intent == "gameplay"
    assert c.interaction_intent == "game_controls"
    assert "canvas_required" in c.runtime_requirements
    assert "runtime_loop_required" in c.runtime_requirements
    assert "input_required" in c.runtime_requirements


def test_canvas_game_requires_game_keywords():
    # Canvas without game keywords → canvas_animation, NOT canvas_game
    c = _classify("canvas animation with drawing and transforms")
    assert c.artifact_type != "canvas_game"


# ---------------------------------------------------------------------------
# Chart visualisation
# ---------------------------------------------------------------------------

def test_chart_visualisation_classified_correctly():
    c = _classify("bar chart showing monthly sales data")
    assert c.artifact_type == "chart_visualization"
    assert c.visual_intent == "data_visualization"


def test_chart_no_animation_requirement():
    c = _classify("pie chart with legend for budget categories")
    assert "animation_required" not in c.runtime_requirements
    assert "game_loop_runs" not in c.runtime_requirements


def test_scatter_plot_classified_as_chart():
    c = _classify("scatter plot visualizing user engagement metrics")
    assert c.artifact_type == "chart_visualization"


# ---------------------------------------------------------------------------
# Unknown / ambiguous
# ---------------------------------------------------------------------------

def test_ambiguous_text_has_low_confidence():
    c = _classify("make something nice")
    assert c.confidence < 0.5


def test_unknown_does_not_inject_game_concepts():
    c = _classify("make something nice")
    # Conservative: unknown must not escalate to canvas_game
    assert c.artifact_type != "canvas_game"
    assert "canvas_required" not in c.runtime_requirements
    assert "game_loop_runs" not in c.runtime_requirements


# ---------------------------------------------------------------------------
# Interactive web app
# ---------------------------------------------------------------------------

def test_interactive_web_app_classified_correctly():
    c = _classify("todo app with add, complete, and delete functionality")
    assert c.artifact_type == "interactive_web_app"
    assert "browser_required" in c.runtime_requirements


# ---------------------------------------------------------------------------
# Classification consistency
# ---------------------------------------------------------------------------

def test_same_input_same_output_determinism():
    text = "animate rainbow colors fading across the page"
    c1 = _classify(text)
    c2 = _classify(text)
    assert c1.artifact_type == c2.artifact_type
    assert c1.visual_intent == c2.visual_intent
    assert c1.runtime_requirements == c2.runtime_requirements
