from __future__ import annotations

from agent.atlas_clarification_gate_service import AtlasClarificationGateService

_GATE = AtlasClarificationGateService()


def test_no_signals_passes():
    result = _GATE.evaluate([])
    assert result['gate_status'] == 'passed'
    assert result['clarification_required'] is False


def test_ambiguous_signals_require_clarification():
    result = _GATE.evaluate(["unclear scope", "multiple interpretations"])
    assert result['clarification_required'] is True
    assert result['gate_status'] == 'clarification_required'
    assert "unclear scope" in result['ambiguity_signals']


def test_safe_default_assumption_bypasses_clarification():
    result = _GATE.evaluate(
        ["unclear color scheme"],
        safe_default_assumption="use blue as default color",
    )
    assert result['clarification_required'] is False
    assert result['gate_status'] == 'proceeded_with_assumption'
    assert result['assumption'] == "use blue as default color"


def test_safety_sensitive_signal_blocks_even_with_default_assumption():
    result = _GATE.evaluate(
        ["unclear execution capability policy"],
        safe_default_assumption="assume allowed",
    )
    assert result['clarification_required'] is True
    assert result['gate_status'] == 'clarification_required'


def test_options_returned_when_provided():
    options = [
        {"option_id": "A", "label": "Option A", "description": "...", "merit": "fast", "risk": "low"},
        {"option_id": "B", "label": "Option B", "description": "...", "merit": "safe", "risk": "medium"},
    ]
    result = _GATE.evaluate(["ambiguous approach"], options=options)
    assert result['clarification_required'] is True
    assert len(result['options']) == 2


def test_detect_ambiguities_finds_markers():
    text = "The scope is unclear and there are multiple interpretations of the requirement."
    signals = _GATE.detect_ambiguities(text)
    assert "unclear" in signals
    assert "multiple interpretations" in signals


def test_detect_ambiguities_returns_empty_for_clear_plan():
    text = "Update index.html to add a blue background color."
    signals = _GATE.detect_ambiguities(text)
    assert signals == []


def test_clarification_unresolved_prevents_patch_apply():
    """When clarification_required=True, callers must not proceed to patch/apply."""
    result = _GATE.evaluate(["scope not defined"])
    assert result['clarification_required'] is True
    # Caller responsibility: do not proceed if clarification_required=True
    assert result['gate_status'] != 'passed'
