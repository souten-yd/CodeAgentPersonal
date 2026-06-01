from __future__ import annotations

from agent.atlas_clarification_gate_service import AtlasClarificationGateService
from agent.atlas_critique_gate_service import AtlasCritiqueGateService
from agent.atlas_critical_event_policy import normalize_critical_event

# Presets / automation levels treated as "full automation policy" (profiles 3-4).
# When selected, high/critical non-safety critique does NOT dead-stop the run: it proceeds
# as a recorded full_auto policy continuation after the planner's post-revision critique.
_FULL_AUTO_PRESETS = frozenset({
    "full_auto",
    "full_auto_multi_item_v1",
    "autonomous_bounded_dev",
    "autonomous_custom",
})
_FULL_AUTO_AUTOMATION_LEVELS = frozenset({"full_autopilot"})

# Keywords marking a finding as safety-sensitive — these always require user
# clarification/approval, even under full_auto.
_SAFETY_SENSITIVE_KEYWORDS = (
    "security", "safety", "auth", "credential", "secret", "token",
    "execution capability", "runtime policy", "run_command", "shell",
    "external access", "network", "permission", "privacy", "data loss",
    "delete", "destructive",
)


def is_full_auto_preset(*, automation_level: str = "", preset_id: str = "") -> bool:
    return (
        str(automation_level or "").strip().lower() in _FULL_AUTO_AUTOMATION_LEVELS
        or str(preset_id or "").strip().lower() in _FULL_AUTO_PRESETS
    )


def _finding_is_safety_sensitive(finding: dict) -> bool:
    if str(finding.get("severity") or "").lower() == "critical":
        return True
    haystack = " ".join(
        str(finding.get(k) or "") for k in ("angle", "category", "title", "detail", "recommendation")
    ).lower()
    return any(kw in haystack for kw in _SAFETY_SENSITIVE_KEYWORDS)


def apply_plan_quality_gate(plan: dict, *, automation_level: str = "", preset_id: str = "", critical_handling: str = "ask") -> dict:
    """Evaluate the critique gate over a planner's (post-revision) plan and decide flow control.

    Returns:
        {
            critique_gate: dict,        # to store in pool.metadata["critique_gate"]
            plan_revision_required: bool,  # block downstream patch generation
            require_approval: bool,        # set pool.status = "approval_required"
            warnings: list[str],
            clarification: dict,           # clarification gate result (options/ambiguity)
        }
    """
    critique_dict = plan.get("adversarial_critique") if isinstance(plan.get("adversarial_critique"), dict) else {}
    gate = AtlasCritiqueGateService().evaluate(critique_dict)

    full_auto = is_full_auto_preset(automation_level=automation_level, preset_id=preset_id)
    warnings: list[str] = []

    if not gate["blocked"]:
        return {
            "critique_gate": {"gate_status": gate["gate_status"]},
            "plan_revision_required": False,
            "require_approval": False,
            "warnings": warnings,
            "clarification": {},
        }

    blocking = gate["blocking_findings"]
    safety_sensitive = any(_finding_is_safety_sensitive(f) for f in blocking)
    residual_risk = str(critique_dict.get("consensus_risk") or "")

    plan_text = " ".join(str(plan.get(k) or "") for k in ("requirement_summary", "goal", "selected_architecture"))

    def _clarification() -> dict:
        # Build clarification options from ambiguity in the plan summary text, if any.
        return AtlasClarificationGateService().evaluate(
            AtlasClarificationGateService().detect_ambiguities(plan_text)
        )

    # ── Critical/safety-sensitive high findings: always pause for user judgment.
    # full_auto, critical_handling=auto, and autonomous_dev_agent are useful for non-critical
    # quality continuation, but they must never silently continue a critical event.
    if safety_sensitive:
        warnings.append("critical_event_detected_waiting_for_user_decision")
        critical_event = normalize_critical_event(
            category="safety_sensitive_critique",
            severity="critical" if any(str(f.get("severity") or "").lower() == "critical" for f in blocking) else "high",
            reason="Safety-sensitive high/critical critique requires explicit user decision",
            affected_files=[],
            affected_capabilities=["plan_critique_gate"],
            estimated_impact="May affect safety, security, data loss, destructive behavior, or runtime execution boundaries.",
            source_gate="plan_critique_gate",
            extra={
                "blocking_findings": blocking,
                "residual_risk": residual_risk,
                "full_auto_bypass_allowed": False,
                "critical_handling_auto_bypass_allowed": False,
            },
        )
        return {
            "critique_gate": {
                "gate_status": "waiting_for_critical_decision",
                "reason": "Critical event detected",
                "residual_risk": residual_risk,
                "blocking_findings": blocking,
                "safety_sensitive": True,
                "critical_event": critical_event,
            },
            "critical_event": critical_event,
            "status": "waiting_for_critical_decision",
            "plan_revision_required": False,
            "require_approval": True,
            "warnings": warnings,
            "clarification": _clarification(),
        }

    # ── Non-safety-sensitive high findings ──
    if full_auto:
        # Recorded full_auto policy continuation — NOT a user-safety override.
        warnings.append("full_auto_continued_with_unresolved_non_safety_critique")
        return {
            "critique_gate": {
                "gate_status": "full_auto_continued",
                "reason": "full_auto_post_revision_continuation",
                "residual_risk": residual_risk,
                "blocking_findings": blocking,
                "auditable_note": "proceeded under full_auto with unresolved non-safety critique",
            },
            "plan_revision_required": False,
            "require_approval": False,
            "warnings": warnings,
            "clarification": {},
        }

    # supervised / lower preset, non-safety high finding → block + ask for revision.
    warnings.append("high_critique_requires_revision")
    return {
        "critique_gate": {
            "gate_status": "blocked",
            "reason": "high_critique_requires_revision",
            "residual_risk": residual_risk,
            "blocking_findings": blocking,
            "safety_sensitive": False,
        },
        "plan_revision_required": True,
        "require_approval": True,
        "warnings": warnings,
        "clarification": _clarification(),
    }
