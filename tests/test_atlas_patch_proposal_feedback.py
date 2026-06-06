"""PF-A: patch proposal verification feedback enrichment tests.

Covers:
  PF-A1: wave_phase_signal key matches and returns the correct repair hint
  PF-A2: _verification_feedback() includes browser_smoke_result for visual failures
  PF-A3: _verification_feedback() includes visual_contract_missing for visual failures
  PF-A4: non-visual failures do not include browser_smoke_result
  PF-A5: all four _SIGNAL_REPAIR_HINTS keys return non-empty strings
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent.atlas_patch_proposal_service import AtlasPatchProposalService


def _make_service() -> AtlasPatchProposalService:
    journal = MagicMock()
    storage = MagicMock()
    return AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=None)


# ---------------------------------------------------------------------------
# PF-A1: wave_phase_signal key is present and returns the correct hint
# ---------------------------------------------------------------------------

def test_wave_phase_signal_repair_hint_present() -> None:
    """wave_phase_signal must map to a hint mentioning Math.sin/cos."""
    svc = _make_service()
    hint = svc._SIGNAL_REPAIR_HINTS.get("wave_phase_signal")
    assert hint is not None, (
        "_SIGNAL_REPAIR_HINTS['wave_phase_signal'] is missing — "
        "was the key left as 'wave_signal'?"
    )
    assert "Math.sin" in hint or "Math.cos" in hint, (
        "wave_phase_signal hint should mention Math.sin/Math.cos"
    )


def test_wave_signal_old_key_no_longer_exists() -> None:
    """The old (incorrect) 'wave_signal' key must not exist any more."""
    svc = _make_service()
    assert "wave_signal" not in svc._SIGNAL_REPAIR_HINTS, (
        "Old 'wave_signal' key should have been renamed to 'wave_phase_signal'"
    )


# ---------------------------------------------------------------------------
# PF-A2/A3: _verification_feedback() includes browser_smoke_result + visual_contract_missing
# ---------------------------------------------------------------------------

def _visual_verification(primary_reason: str, missing: list[str], smoke_status: str, smoke_reason: str) -> dict:
    return {
        "status": "failed",
        "warnings": ["visual_contract_failed", f"visual_missing:{missing[0]}"] if missing else ["visual_contract_failed"],
        "metadata": {
            "primary_verification_reason": primary_reason,
            "visual_contract": {
                "status": "failed",
                "missing": missing,
            },
            "browser_smoke": {
                "status": smoke_status,
                "reason": smoke_reason,
                "diagnostics": {
                    "style_changed": False,
                    "canvas": {"present": True, "changed": False},
                },
                "console_errors": [],
            },
        },
    }


def test_verification_feedback_includes_browser_smoke_for_wave_phase_failure() -> None:
    svc = _make_service()
    vr = _visual_verification(
        primary_reason="visual_missing:wave_phase_signal",
        missing=["wave_phase_signal"],
        smoke_status="browser_smoke_failed",
        smoke_reason="animation_not_detected",
    )
    payload = {
        "latest_verification": vr,
        "item": {},
    }
    feedback = svc._verification_feedback(payload)
    assert feedback is not None
    assert "browser_smoke_result" in feedback, (
        "_verification_feedback must include browser_smoke_result for visual_missing failures"
    )
    bsr = feedback["browser_smoke_result"]
    assert bsr["canvas_present"] is True
    assert bsr["canvas_changed"] is False
    assert bsr["style_changed"] is False


def test_verification_feedback_includes_visual_contract_missing() -> None:
    svc = _make_service()
    vr = _visual_verification(
        primary_reason="visual_missing:wave_phase_signal",
        missing=["wave_phase_signal"],
        smoke_status="browser_smoke_failed",
        smoke_reason="animation_not_detected",
    )
    payload = {"latest_verification": vr, "item": {}}
    feedback = svc._verification_feedback(payload)
    assert "visual_contract_missing" in feedback
    assert "wave_phase_signal" in feedback["visual_contract_missing"]


def test_verification_feedback_smoke_for_animation_not_detected_in_reason() -> None:
    """primary_reason that directly contains animation_not_detected also triggers smoke inclusion."""
    svc = _make_service()
    vr = {
        "status": "failed",
        "warnings": ["visual_contract_failed"],
        "metadata": {
            "primary_verification_reason": "browser_smoke_failed:animation_not_detected",
            "visual_contract": {"status": "failed", "missing": ["animation_signal"]},
            "browser_smoke": {
                "status": "browser_smoke_failed",
                "reason": "animation_not_detected",
                "diagnostics": {"style_changed": False, "canvas": {}},
                "console_errors": ["some error"],
            },
        },
    }
    feedback = svc._verification_feedback({"latest_verification": vr, "item": {}})
    assert feedback is not None
    assert "browser_smoke_result" in feedback
    assert feedback["browser_smoke_result"]["console_errors"] == ["some error"]


# ---------------------------------------------------------------------------
# PF-A4: non-visual failures do NOT include browser_smoke_result
# ---------------------------------------------------------------------------

def test_verification_feedback_no_smoke_for_pytest_failure() -> None:
    svc = _make_service()
    vr = {
        "status": "failed",
        "warnings": ["test_failed"],
        "metadata": {},
        "command": "python -m pytest -q tests/test_foo.py",
        "exit_code": 1,
        "stdout_tail": "FAILED tests/test_foo.py::test_bar",
        "stderr_tail": "",
    }
    feedback = svc._verification_feedback({"latest_verification": vr, "item": {}})
    assert feedback is not None
    assert "browser_smoke_result" not in feedback
    assert "visual_contract_missing" not in feedback


# ---------------------------------------------------------------------------
# PF-A5: all four _SIGNAL_REPAIR_HINTS keys produce non-empty strings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("signal", ["color_mutation_signal", "animation_signal", "motion_signal", "wave_phase_signal"])
def test_all_signal_hints_non_empty(signal: str) -> None:
    svc = _make_service()
    hint = svc._SIGNAL_REPAIR_HINTS.get(signal)
    assert hint, f"_SIGNAL_REPAIR_HINTS['{signal}'] is missing or empty"


# ---------------------------------------------------------------------------
# PF-A6: _verification_repair_instruction uses the wave_phase_signal hint
# ---------------------------------------------------------------------------

def test_repair_instruction_includes_wave_hint() -> None:
    svc = _make_service()
    instruction = svc._verification_repair_instruction("visual_missing:wave_phase_signal")
    assert "Math.sin" in instruction or "Math.cos" in instruction, (
        "Repair instruction for wave_phase_signal must include Math.sin/Math.cos guidance"
    )
    assert "wave" in instruction.lower() or "phase" in instruction.lower()
