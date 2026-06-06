"""Unit tests for VisualContractRegistry — MVP universal contract.

The registry now always returns universal_visual_v1 so no per-type contract
configuration is needed when adding new artifact types (HTML, Web, Game,
Business apps all pass the same gate).

Specialised contracts (static_html_visual_v1, canvas_game_visual_v1, etc.)
still exist and are reachable via get(), but select() always returns universal.
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
# MVP universal contract — select() always returns universal_visual_v1
# ---------------------------------------------------------------------------

def test_all_artifact_types_get_universal_contract():
    tasks = [
        "make a simple HTML page",
        "animate the text with rainbow colors",
        "form with name, email, and submit button",
        "canvas particle animation with requestAnimationFrame",
        "browser game with score, player, and collision on canvas",
        "bar chart showing sales data by month",
        "interactive todo app with add and delete",
        "business dashboard with KPI widgets",
    ]
    for task in tasks:
        c = _contract_for(task)
        assert c.contract_id == "universal_visual_v1", (
            f"Expected universal_visual_v1 for '{task}', got {c.contract_id}"
        )


def test_universal_contract_only_requires_page_loads():
    c = _reg.get("universal_visual_v1")
    assert c is not None
    assert c.required_signals == ["page_loads"]
    # All other signals are optional — no hard task-specific requirements
    assert "animation_signal" not in c.required_signals
    assert "canvas_exists" not in c.required_signals
    assert "game_loop_runs" not in c.required_signals


def test_universal_contract_has_no_forbidden_signals():
    c = _reg.get("universal_visual_v1")
    assert c is not None
    assert c.forbidden_signals == [], (
        "universal_visual_v1 must not forbid any signals — it works for all artifact types"
    )


def test_universal_contract_uses_universal_repair_profile():
    c = _reg.get("universal_visual_v1")
    assert c is not None
    assert c.repair_profile == "universal_visual_repair"


def test_select_returns_universal_for_low_confidence():
    low_cls = _make_classification(artifact_type="animated_html_page", confidence=0.1)
    c = _reg.select(low_cls)
    assert c.contract_id == "universal_visual_v1"


def test_select_returns_universal_for_unknown_artifact_type():
    unknown_cls = _make_classification(artifact_type="unknown", confidence=0.9)
    c = _reg.select(unknown_cls)
    assert c.contract_id == "universal_visual_v1"


def test_select_is_deterministic():
    text = "animate text with rainbow hue shifting"
    n = _norm.normalize(text)
    cls = _clf.classify(n, text)
    c1 = _reg.select(cls)
    c2 = _reg.select(cls)
    assert c1.contract_id == c2.contract_id == "universal_visual_v1"


# ---------------------------------------------------------------------------
# Specialised contracts still accessible via get() for future opt-in use
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cid", [
    "static_html_visual_v1",
    "animated_dom_visual_v1",
    "ui_component_visual_v1",
    "interactive_web_app_visual_v1",
    "canvas_animation_visual_v1",
    "canvas_game_visual_v1",
    "chart_visualization_v1",
    "universal_visual_v1",
])
def test_specialised_contracts_still_retrievable(cid: str):
    c = _reg.get(cid)
    assert c is not None, f"{cid} not found in registry"
    assert c.contract_id == cid
    assert len(c.required_signals) > 0
    assert c.repair_profile


def test_get_returns_none_for_unknown_id():
    assert _reg.get("nonexistent_contract_id") is None


# ---------------------------------------------------------------------------
# Contract completeness
# ---------------------------------------------------------------------------

def test_all_contracts_have_verification_method():
    for cid in _reg.all_ids():
        c = _reg.get(cid)
        assert c.verification_method in ("static_only", "smoke_optional", "smoke_required"), (
            f"{cid} has invalid verification_method: {c.verification_method}"
        )


def test_universal_optional_signals_cover_all_artifact_types():
    c = _reg.get("universal_visual_v1")
    assert c is not None
    # Should cover animation, canvas, chart, and interaction signal families
    for signal in ("animation_signal", "canvas_exists", "chart_element_exists", "required_controls_exist"):
        assert signal in c.optional_signals, f"universal_visual_v1 optional_signals missing {signal}"
