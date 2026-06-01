"""Auto-verification failures surface the precise reason, not a bare verification_failed.

Regression for the run that stopped at ``Summary stops: verification_failed`` without
exposing the underlying browser/visual reason.
"""

from __future__ import annotations

from types import SimpleNamespace

from agent.atlas_failure_stop_service import (
    AtlasFailureStopService,
    _primary_verification_reason,
)
from agent.atlas_multi_item_autopilot_service import primary_verification_reason


def test_primary_reason_prefers_hard_browser_error() -> None:
    warnings = ["visual_contract_passed", "browser_smoke_failed:js_error"]
    assert primary_verification_reason(warnings) == "browser_smoke_failed:js_error"


def test_primary_reason_visual_missing() -> None:
    warnings = ["visual_contract_failed", "visual_missing:animation_signal"]
    # visual_contract_failed has higher priority than the specific missing signal.
    assert primary_verification_reason(warnings) == "visual_contract_failed"


def test_primary_reason_ignores_soft_warnings() -> None:
    warnings = ["visual_contract_passed", "browser_smoke_warning:animation_not_detected_no_style_change"]
    assert primary_verification_reason(warnings) == ""


def test_primary_reason_empty() -> None:
    assert primary_verification_reason([]) == ""


class _Journal:
    def append_event(self, *args, **kwargs) -> None:  # pragma: no cover - no-op
        return None


def _build_suggestion(warnings):
    service = AtlasFailureStopService(journal=_Journal())
    pool = SimpleNamespace(pool_id="pool_1")
    item = SimpleNamespace(item_id="item_1", metadata={})
    verification_result = {"status": "failed", "warnings": warnings}
    return service.build_for_verification_failure(pool, item, "run_1", verification_result)


def test_failure_stop_suggestion_surfaces_precise_reason() -> None:
    suggestion = _build_suggestion(["browser_smoke_failed:js_error"])
    assert suggestion.metadata["primary_verification_reason"] == "browser_smoke_failed:js_error"
    assert suggestion.suggested_manual_actions[0] == "Verification failed: browser_smoke_failed:js_error"
    # Full verification detail is retained for the UI / recovery.
    assert suggestion.verification_result["warnings"] == ["browser_smoke_failed:js_error"]
    # The stable headline reason is unchanged so existing consumers still match.
    assert suggestion.reason == "auto_verification_failed_after_safe_apply"


def test_failure_stop_helper_matches_service() -> None:
    vr = {"status": "failed", "warnings": ["visual_missing:motion_signal"]}
    assert _primary_verification_reason(vr) == "visual_missing:motion_signal"
