"""
Structured failure taxonomy for visual verification.

Every failure in the visual pipeline is represented as a VisualVerificationFailure
with enough context for:
  - the repair planner to select a profile,
  - the UI to show actionable recovery controls,
  - debugging without guessing which contract was used.

build_failure() is the preferred factory — it fills defaults from the contract's
failure_message_template and enforces consistency.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Failure type constants
# ---------------------------------------------------------------------------

FAILURE_TYPES = [
    "requirement_normalization_ambiguous",  # normalizer found unresolved ambiguities
    "task_classification_uncertain",        # classifier confidence too low
    "visual_contract_mismatch",             # contract doesn't match observed artifact
    "visual_contract_failed",               # contract's required signals not satisfied
    "browser_load_failed",                  # page did not load in browser
    "browser_console_error",               # JS error detected in browser console
    "runtime_signal_missing",              # expected runtime attribute/signal absent
    "runtime_signal_static",               # signal exists but shows no change over time
    "motion_not_detected",                 # no style/transform/position change
    "color_change_not_detected",           # no colour change detected
    "interaction_not_detected",            # expected UI interaction had no effect
    "canvas_frame_not_detected",           # canvas pixel hash unchanged
    "accessibility_check_failed",          # missing labels, ARIA, or contrast
    "performance_warning",                 # excessive DOM churn or layout thrashing
    "repair_not_safe",                     # repair cannot be inferred safely
    "snapshot_unavailable",                # no snapshot to restore from
]

SEVERITIES = ["error", "warning", "advisory"]


# ---------------------------------------------------------------------------
# Failure model
# ---------------------------------------------------------------------------

@dataclass
class VisualVerificationFailure:
    failure_type: str         # value from FAILURE_TYPES
    contract_id: str
    failed_signal: str        # the specific signal that was missing or broken

    severity: str = "error"   # "error" | "warning" | "advisory"
    artifact_type: str = ""
    visual_intent: str = ""
    explanation: str = ""
    suggested_repair_profile: str = ""

    # Whether the repair planner can attempt automatic repair for this failure
    auto_repair_allowed: bool = False
    # Whether the planner should re-classify the task before retrying
    plan_revision_recommended: bool = False
    # Whether the user should be asked to clarify the requirement
    clarification_recommended: bool = False

    # Freeform additional context (e.g. console error text, diff snippets)
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "failure_type": self.failure_type,
            "contract_id": self.contract_id,
            "failed_signal": self.failed_signal,
            "severity": self.severity,
            "artifact_type": self.artifact_type,
            "visual_intent": self.visual_intent,
            "explanation": self.explanation,
            "suggested_repair_profile": self.suggested_repair_profile,
            "auto_repair_allowed": self.auto_repair_allowed,
            "plan_revision_recommended": self.plan_revision_recommended,
            "clarification_recommended": self.clarification_recommended,
            "diagnostics": self.diagnostics,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_failure(
    *,
    failure_type: str,
    contract_id: str,
    failed_signal: str,
    repair_profile: str,
    failure_message_template: str = "",
    severity: str = "error",
    artifact_type: str = "",
    visual_intent: str = "",
    auto_repair_allowed: bool = True,  # safe default; repair_not_safe should pass False
    plan_revision_recommended: bool = False,
    clarification_recommended: bool = False,
    diagnostics: dict | None = None,
) -> VisualVerificationFailure:
    """
    Create a VisualVerificationFailure with a human-readable explanation.

    The explanation is built from the contract's failure_message_template
    by substituting {signal}.  Falls back to a generic message if the template
    is absent.
    """
    if failure_message_template:
        explanation = failure_message_template.format(signal=failed_signal)
    else:
        explanation = (
            f"Contract '{contract_id}' failed: required signal '{failed_signal}' "
            f"was not satisfied (failure_type={failure_type})."
        )

    return VisualVerificationFailure(
        failure_type=failure_type,
        contract_id=contract_id,
        failed_signal=failed_signal,
        severity=severity,
        artifact_type=artifact_type,
        visual_intent=visual_intent,
        explanation=explanation,
        suggested_repair_profile=repair_profile,
        auto_repair_allowed=auto_repair_allowed,
        plan_revision_recommended=plan_revision_recommended,
        clarification_recommended=clarification_recommended,
        diagnostics=diagnostics or {},
    )


# ---------------------------------------------------------------------------
# Helpers for collecting failures from raw verifier results
# ---------------------------------------------------------------------------

def failures_from_missing_signals(
    missing_signals: list[str],
    *,
    contract_id: str,
    repair_profile: str,
    failure_message_template: str,
    artifact_type: str = "",
    visual_intent: str = "",
    auto_repair_allowed: bool = True,
) -> list[VisualVerificationFailure]:
    """
    Convert a list of missing signal names into structured failures.

    Each missing signal becomes a separate VisualVerificationFailure so the
    repair planner can address them individually.
    """
    results: list[VisualVerificationFailure] = []
    for signal in missing_signals:
        # Determine failure type from signal name
        ft = _signal_to_failure_type(signal)
        results.append(build_failure(
            failure_type=ft,
            contract_id=contract_id,
            failed_signal=signal,
            repair_profile=repair_profile,
            failure_message_template=failure_message_template,
            artifact_type=artifact_type,
            visual_intent=visual_intent,
            auto_repair_allowed=auto_repair_allowed,
        ))
    return results


def _signal_to_failure_type(signal: str) -> str:
    """Map a signal name to the most appropriate failure type."""
    s = signal.lower()
    if "page_loads" in s or "browser_load" in s:
        return "browser_load_failed"
    if "console" in s or "js_error" in s:
        return "browser_console_error"
    if "animation_signal" in s or "animation" in s:
        return "runtime_signal_missing"
    if "style_change" in s or "motion" in s:
        return "motion_not_detected"
    if "color_change" in s or "colour_change" in s:
        return "color_change_not_detected"
    if "canvas_frame" in s or "frame_changes" in s:
        return "canvas_frame_not_detected"
    if "interaction" in s or "state_changes" in s:
        return "interaction_not_detected"
    if "accessibility" in s or "aria" in s or "label" in s:
        return "accessibility_check_failed"
    return "visual_contract_failed"
