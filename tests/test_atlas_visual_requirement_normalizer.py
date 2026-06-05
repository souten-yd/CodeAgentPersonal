"""Unit tests for VisualRequirementNormalizer."""
from __future__ import annotations

import pytest

from agent.atlas_visual_requirement_normalizer import (
    NormalizedVisualRequirement,
    VisualRequirementNormalizer,
)

_norm = VisualRequirementNormalizer()


def test_empty_string_returns_safe_defaults():
    r = _norm.normalize("")
    assert isinstance(r, NormalizedVisualRequirement)
    assert r.raw_requirement == ""
    assert r.clarification_required is False
    assert r.confidence == 1.0


def test_hz_frequency_extracted():
    r = _norm.normalize("make the text pulse at 2 Hz")
    assert r.animation_frequency_hz == pytest.approx(2.0)
    assert "animation_required" in r.runtime_requirements


def test_hz_lowercase_extracted():
    r = _norm.normalize("oscillate at 0.5hz")
    assert r.animation_frequency_hz == pytest.approx(0.5)


def test_once_per_second_normalised_to_1hz():
    r = _norm.normalize("the color should change once per second")
    assert r.animation_frequency_hz == pytest.approx(1.0)


def test_times_per_second():
    r = _norm.normalize("flash 3 times per second")
    assert r.animation_frequency_hz == pytest.approx(3.0)


def test_fps_stored_proportionally():
    r = _norm.normalize("animation runs at 60fps")
    # 60fps / 60 = 1.0 Hz relative
    assert r.animation_frequency_hz == pytest.approx(1.0)


def test_seconds_duration():
    r = _norm.normalize("animate for 3 seconds")
    assert r.animation_duration_seconds == pytest.approx(3.0)
    assert "animation_required" in r.runtime_requirements


def test_milliseconds_duration():
    r = _norm.normalize("fade in over 500ms")
    assert r.animation_duration_seconds == pytest.approx(0.5)


def test_minutes_duration():
    r = _norm.normalize("loop for 2 minutes")
    assert r.animation_duration_seconds == pytest.approx(120.0)


def test_loop_forever_is_infinite_sentinel():
    r = _norm.normalize("loop forever with a color animation")
    assert r.animation_duration_seconds == -1.0


def test_motion_types_wave():
    r = _norm.normalize("create a wave effect")
    assert "wave" in r.motion_types


def test_motion_types_bounce():
    r = _norm.normalize("make the ball bounce")
    assert "bounce" in r.motion_types


def test_motion_types_rotate():
    r = _norm.normalize("rotate the logo slowly")
    assert "rotate" in r.motion_types


def test_color_types_rainbow():
    r = _norm.normalize("display rainbow colors in the header")
    assert "rainbow" in r.color_types
    assert "animation_required" in r.runtime_requirements


def test_color_types_hue_cycle():
    r = _norm.normalize("hue cycle through the spectrum")
    assert "hue-cycle" in r.color_types


def test_color_types_gradient():
    r = _norm.normalize("animate a gradient background")
    assert "gradient" in r.color_types


def test_color_types_random_color():
    r = _norm.normalize("random color changes every frame")
    assert "random-color" in r.color_types


def test_interaction_click():
    r = _norm.normalize("click to start the animation")
    assert "click" in r.interaction_types
    assert "input_required" in r.runtime_requirements


def test_interaction_keyboard():
    r = _norm.normalize("keyboard controls for the character")
    assert "keyboard" in r.interaction_types
    assert "input_required" in r.runtime_requirements


def test_interaction_drag():
    r = _norm.normalize("drag and drop items")
    assert "drag" in r.interaction_types


def test_interaction_form():
    r = _norm.normalize("a form with text input and submit")
    assert "form" in r.interaction_types
    assert "input_required" in r.runtime_requirements


def test_rendering_target_canvas():
    r = _norm.normalize("draw particles on a canvas element")
    assert r.rendering_target == "canvas"
    assert "canvas_required" in r.runtime_requirements


def test_rendering_target_webgl_beats_canvas():
    r = _norm.normalize("WebGL shader animation on a canvas")
    assert r.rendering_target == "webgl"
    assert "webgl_required" in r.runtime_requirements


def test_rendering_target_svg():
    r = _norm.normalize("SVG animation of morphing shapes")
    assert r.rendering_target == "svg"
    assert "svg_required" in r.runtime_requirements


def test_rendering_target_html_page():
    r = _norm.normalize("make a simple HTML page with text")
    assert r.rendering_target == "html"


def test_ambiguous_animation_speed_records_assumption_not_clarification():
    r = _norm.normalize("make the animation speed smooth")
    assert any("speed" in a or "smooth" in a for a in r.assumptions + r.unresolved_ambiguities)
    # cosmetic ambiguity — clarification NOT required
    assert r.clarification_required is False
    assert r.confidence < 1.0


def test_source_phrases_populated():
    r = _norm.normalize("make a rainbow wave")
    assert len(r.source_phrases) > 0
    # should contain something related to rainbow or wave
    combined = " ".join(r.source_phrases).lower()
    assert "rainbow" in combined or "wave" in combined


def test_no_false_positive_animation_for_static_page():
    r = _norm.normalize("create a simple static HTML page with company information")
    # Static page should not require animation
    assert "animation_required" not in r.runtime_requirements
    assert r.motion_types == []
    assert r.color_types == []


def test_canvas_game_sets_game_hint():
    r = _norm.normalize("browser game with score and lives on a canvas")
    assert "canvas" in r.artifact_type_hints
    assert "game" in r.artifact_type_hints
    assert "input_required" in r.runtime_requirements
    assert "runtime_loop_required" in r.runtime_requirements


def test_per_frame_sets_runtime_loop():
    r = _norm.normalize("update the position per frame")
    assert "runtime_loop_required" in r.runtime_requirements


def test_browser_required_for_any_visual_hint():
    r = _norm.normalize("build an HTML component")
    assert "browser_required" in r.runtime_requirements
