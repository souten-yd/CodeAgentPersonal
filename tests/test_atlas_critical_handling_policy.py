"""critical_handling defaults are profile/preset/envelope dependent, not a blanket auto."""

from __future__ import annotations

import pytest

from agent.atlas_critical_handling_policy import (
    CRITICAL_HANDLING_BY_PROFILE,
    normalize_critical_handling,
    resolve_default_critical_handling,
)


def test_profile_defaults_are_safe() -> None:
    assert CRITICAL_HANDLING_BY_PROFILE["review_only"] == "block"
    assert CRITICAL_HANDLING_BY_PROFILE["guarded_single_action"] == "ask"
    assert CRITICAL_HANDLING_BY_PROFILE["supervised_bounded_auto"] == "ask"
    # The profile alone (no preset/envelope signal) stays conservative.
    assert CRITICAL_HANDLING_BY_PROFILE["autonomous_dev_agent"] == "ask"


@pytest.mark.parametrize(
    "preset,expected",
    [
        ("review_only", "block"),
        ("single_action", "ask"),
        ("supervised_auto", "ask"),
        ("autonomous_custom", "auto"),
        ("autonomous_bounded_dev", "auto"),
        ("full_auto", "auto"),
    ],
)
def test_preset_defaults(preset: str, expected: str) -> None:
    assert resolve_default_critical_handling(preset_id=preset) == expected


def test_unknown_context_defaults_to_ask_not_auto() -> None:
    assert resolve_default_critical_handling() == "ask"
    assert resolve_default_critical_handling(preset_id="mystery") == "ask"


def test_explicit_value_always_wins() -> None:
    assert resolve_default_critical_handling(preset_id="autonomous_bounded_dev", explicit="block") == "block"
    assert resolve_default_critical_handling(preset_id="review_only", explicit="auto") == "auto"
    # Unrecognised explicit values are ignored (fall through to the resolved default).
    assert resolve_default_critical_handling(preset_id="review_only", explicit="bogus") == "block"


def test_self_improvement_envelope_stays_ask() -> None:
    assert resolve_default_critical_handling(self_improvement=True, preset_id="autonomous_bounded_dev") == "ask"
    assert (
        resolve_default_critical_handling(
            envelope_id="pre_authorized_self_improvement_envelope",
            strict_gate_approved=True,
            envelope_active=True,
        )
        == "ask"
    )


def test_normalize_critical_handling() -> None:
    assert normalize_critical_handling("AUTO") == "auto"
    assert normalize_critical_handling(" ask ") == "ask"
    assert normalize_critical_handling("nonsense") is None
    assert normalize_critical_handling(None) is None
