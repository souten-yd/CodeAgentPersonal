"""Unit tests for atlas_visual_failure_taxonomy."""
from __future__ import annotations

import pytest

from agent.atlas_visual_failure_taxonomy import (
    FAILURE_TYPES,
    VisualVerificationFailure,
    build_failure,
    failures_from_missing_signals,
    _signal_to_failure_type,
)


def test_build_failure_produces_correct_type():
    f = build_failure(
        failure_type="visual_contract_failed",
        contract_id="animated_dom_visual_v1",
        failed_signal="animation_signal",
        repair_profile="animated_dom_repair",
        failure_message_template="Animated DOM contract failed: {signal} was not detected.",
    )
    assert f.failure_type == "visual_contract_failed"
    assert f.contract_id == "animated_dom_visual_v1"
    assert f.failed_signal == "animation_signal"
    assert "animation_signal" in f.explanation


def test_build_failure_template_substitution():
    f = build_failure(
        failure_type="motion_not_detected",
        contract_id="animated_dom_visual_v1",
        failed_signal="style_change_over_time",
        repair_profile="animated_dom_repair",
        failure_message_template="Contract '{signal}' check failed.",
    )
    assert "style_change_over_time" in f.explanation


def test_build_failure_fallback_explanation_when_no_template():
    f = build_failure(
        failure_type="visual_contract_failed",
        contract_id="static_html_visual_v1",
        failed_signal="page_loads",
        repair_profile="static_html_repair",
    )
    assert "page_loads" in f.explanation
    assert "static_html_visual_v1" in f.explanation


def test_build_failure_repair_not_safe_disallows_auto_repair():
    f = build_failure(
        failure_type="repair_not_safe",
        contract_id="canvas_game_visual_v1",
        failed_signal="game_loop_runs",
        repair_profile="canvas_game_repair",
        auto_repair_allowed=False,
    )
    assert f.auto_repair_allowed is False


def test_non_game_failure_does_not_suggest_game_repair():
    f = build_failure(
        failure_type="motion_not_detected",
        contract_id="animated_dom_visual_v1",
        failed_signal="style_change_over_time",
        repair_profile="animated_dom_repair",
    )
    # The repair profile must NOT be a game profile
    assert f.suggested_repair_profile == "animated_dom_repair"
    assert "game" not in f.suggested_repair_profile


def test_failures_from_missing_signals_produces_one_failure_per_signal():
    signals = ["animation_signal", "style_change_over_time", "color_change_detectable"]
    failures = failures_from_missing_signals(
        signals,
        contract_id="animated_dom_visual_v1",
        repair_profile="animated_dom_repair",
        failure_message_template="Contract failed: {signal}.",
    )
    assert len(failures) == 3
    returned_signals = {f.failed_signal for f in failures}
    assert returned_signals == set(signals)


def test_failures_from_missing_signals_empty_list():
    failures = failures_from_missing_signals(
        [],
        contract_id="static_html_visual_v1",
        repair_profile="static_html_repair",
        failure_message_template="",
    )
    assert failures == []


def test_signal_to_failure_type_page_loads():
    ft = _signal_to_failure_type("page_loads")
    assert ft == "browser_load_failed"


def test_signal_to_failure_type_animation():
    ft = _signal_to_failure_type("animation_signal")
    assert ft == "runtime_signal_missing"


def test_signal_to_failure_type_motion():
    ft = _signal_to_failure_type("style_change_over_time")
    assert ft == "motion_not_detected"


def test_signal_to_failure_type_color():
    ft = _signal_to_failure_type("color_change_detectable")
    assert ft == "color_change_not_detected"


def test_signal_to_failure_type_canvas():
    ft = _signal_to_failure_type("frame_changes_over_time")
    assert ft == "canvas_frame_not_detected"


def test_signal_to_failure_type_interaction():
    ft = _signal_to_failure_type("state_changes_on_interaction")
    assert ft == "interaction_not_detected"


def test_signal_to_failure_type_fallback():
    ft = _signal_to_failure_type("unknown_custom_signal")
    assert ft == "visual_contract_failed"


def test_all_failure_types_are_strings():
    for ft in FAILURE_TYPES:
        assert isinstance(ft, str)
        assert len(ft) > 0


def test_failure_to_dict_round_trips():
    f = build_failure(
        failure_type="visual_contract_failed",
        contract_id="chart_visualization_v1",
        failed_signal="chart_element_exists",
        repair_profile="chart_repair",
        severity="error",
        artifact_type="chart_visualization",
        visual_intent="data_visualization",
        auto_repair_allowed=True,
        plan_revision_recommended=False,
        clarification_recommended=False,
    )
    d = f.to_dict()
    assert d["failure_type"] == "visual_contract_failed"
    assert d["contract_id"] == "chart_visualization_v1"
    assert d["failed_signal"] == "chart_element_exists"
    assert d["severity"] == "error"
    assert d["auto_repair_allowed"] is True
