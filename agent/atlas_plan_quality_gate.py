from __future__ import annotations

from agent.atlas_clarification_gate_service import AtlasClarificationGateService
from agent.atlas_critique_gate_service import AtlasCritiqueGateService

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


def apply_plan_quality_gate(plan: dict, *, automation_level: str = "", preset_id: str = "") -> dict:
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

    if full_auto and not safety_sensitive:
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

    # supervised / lower preset, OR safety-sensitive high finding under any preset → block + ask.
    reason = "safety_sensitive_high_critique" if safety_sensitive else "high_critique_requires_revision"
    warnings.append(reason)
    # Build clarification options from ambiguity in the plan summary text, if any.
    plan_text = " ".join(str(plan.get(k) or "") for k in ("requirement_summary", "goal", "selected_architecture"))
    clarification = AtlasClarificationGateService().evaluate(
        AtlasClarificationGateService().detect_ambiguities(plan_text)
    )
    return {
        "critique_gate": {
            "gate_status": "blocked",
            "reason": reason,
            "residual_risk": residual_risk,
            "blocking_findings": blocking,
            "safety_sensitive": safety_sensitive,
        },
        "plan_revision_required": True,
        "require_approval": True,
        "warnings": warnings,
        "clarification": clarification,
    }
