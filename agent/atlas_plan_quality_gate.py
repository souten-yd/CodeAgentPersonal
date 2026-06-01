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

    # ── Safety-sensitive high/critical findings: routed by the configurable critical_handling knob.
    # This is the single human-in-the-loop boundary shared with the apply-time full_auto gate.
    if safety_sensitive:
        # The plan-time critique gate keeps a conservative "ask" default for every preset:
        # it is the earliest human-in-the-loop boundary, so by default it pauses for a user
        # decision (without forcing a re-plan). An explicit critical_handling value still
        # unlocks full autonomy ("auto") or a hard stop ("block"). Profile/preset/envelope
        # *default* relaxation to "auto" is applied at the apply layer (safe_apply adapter /
        # full_auto gate), not here.
        handling = str(critical_handling or "ask").strip().lower()
        if handling == "auto":
            # Maximum autonomy — proceed without approval but record an audit trail.
            warnings.append("critical_handling_auto_continued_safety_sensitive")
            return {
                "critique_gate": {
                    "gate_status": "critical_auto_continued",
                    "reason": "safety_sensitive_high_critique",
                    "residual_risk": residual_risk,
                    "blocking_findings": blocking,
                    "safety_sensitive": True,
                    "auditable_note": "proceeded under critical_handling=auto despite safety-sensitive critique",
                },
                "plan_revision_required": False,
                "require_approval": False,
                "warnings": warnings,
                "clarification": {},
            }
        if handling == "ask":
            # Pause for a user decision (approval/clarification) but do NOT force a re-plan.
            warnings.append("safety_sensitive_high_critique_ask")
            return {
                "critique_gate": {
                    "gate_status": "ask",
                    "reason": "safety_sensitive_high_critique",
                    "residual_risk": residual_risk,
                    "blocking_findings": blocking,
                    "safety_sensitive": True,
                },
                "plan_revision_required": False,
                "require_approval": True,
                "warnings": warnings,
                "clarification": _clarification(),
            }
        # block (default for safety): stop and require a revised plan.
        warnings.append("safety_sensitive_high_critique")
        return {
            "critique_gate": {
                "gate_status": "blocked",
                "reason": "safety_sensitive_high_critique",
                "residual_risk": residual_risk,
                "blocking_findings": blocking,
                "safety_sensitive": True,
            },
            "plan_revision_required": True,
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
