from __future__ import annotations

from agent.atlas_clarification_gate_service import AtlasClarificationGateService
from agent.atlas_critique_gate_service import AtlasCritiqueGateService
from agent.atlas_automation_profile_resolver import is_full_auto_context
from agent.atlas_critical_event_policy import normalize_critical_event

# Keywords marking a finding as safety-sensitive — these always require user
# clarification/approval, even under full_auto.
_SAFETY_SENSITIVE_KEYWORDS = (
    "security", "safety", "auth", "credential", "secret", "token",
    "execution capability", "runtime policy", "run_command", "shell",
    "external access", "network", "permission", "privacy", "data loss",
    "delete", "destructive",
)


def is_full_auto_preset(*, automation_level: str = "", preset_id: str = "") -> bool:
    return is_full_auto_context(preset_id=preset_id, automation_level=automation_level)


# File extensions that are non-executable browser/frontend assets. A plan whose entire
# change scope is these (and which does not delete or run commands) is confined to the
# project's sandbox working folder and carries no safety blast radius of its own.
_SANDBOX_FRONTEND_EXTENSIONS = (".html", ".htm", ".css", ".js", ".mjs", ".json", ".md", ".txt", ".svg")
_EXECUTABLE_EXTENSIONS = (".py", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".sql", ".yaml", ".yml", ".toml")


def _finding_is_safety_sensitive(finding: dict, *, allow_severity_escalation: bool = True) -> bool:
    haystack = " ".join(
        str(finding.get(k) or "") for k in ("angle", "category", "title", "detail", "recommendation")
    ).lower()
    if any(kw in haystack for kw in _SAFETY_SENSITIVE_KEYWORDS):
        return True
    # A raw "critical" SEVERITY label escalates to a safety decision only when we cannot prove the
    # change is confined to the project's sandbox. For sandbox-only frontend work a "critical"
    # QUALITY/logic critique (e.g. "Logical Contradiction") is not a safety risk — it routes through
    # the normal quality gate (revise/approve or full_auto continuation) instead of a critical
    # SAFETY event, so the user is not asked to approve a "重大リスク" for a bounded, non-destructive
    # edit under their own working folder.
    if allow_severity_escalation and str(finding.get("severity") or "").lower() == "critical":
        return True
    return False


def _plan_change_scope(plan: dict) -> list[str]:
    files: list[str] = []
    steps = plan.get("implementation_steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                for f in step.get("target_files") or []:
                    if str(f).strip():
                        files.append(str(f).strip())
    for f in plan.get("target_files") or []:
        if str(f).strip():
            files.append(str(f).strip())
    return files


def _plan_is_sandbox_frontend_only(plan: dict) -> bool:
    """True when the plan's whole change scope is non-executable frontend files (no destructive or
    command-execution steps). Such a plan only edits files under the project's sandbox working
    folder, so a non-safety-keyword quality critique should not be escalated to a critical safety
    event. Returns False when the scope is unknown (empty) — we only downgrade when we can PROVE
    the change is bounded."""
    files = _plan_change_scope(plan)
    if not files:
        return False
    normalized = [f.replace("\\", "/").lower() for f in files]
    if any(("/" == n[:1]) or (".." in n.split("/")) for n in normalized):
        return False  # escapes the project root
    if any(n.endswith(_EXECUTABLE_EXTENSIONS) for n in normalized):
        return False
    if not all(n.endswith(_SANDBOX_FRONTEND_EXTENSIONS) for n in normalized):
        return False
    steps = plan.get("implementation_steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and str(step.get("action_type") or "").lower() in {"delete", "run_command"}:
                return False
    return True


def apply_plan_quality_gate(plan: dict, *, automation_level: str = "", preset_id: str = "", critical_handling: str = "ask", quality_gate_enforcement: str = "block") -> dict:
    """Evaluate the critique gate over a planner's (post-revision) plan and decide flow control.

    ``quality_gate_enforcement`` mirrors the rest of the pipeline (depth gate, safe-apply executor,
    multi-item autopilot): only ``"block"`` hard-blocks; ``"warn"`` surfaces the same findings as
    warnings WITHOUT setting ``plan_revision_required`` (which downstream ``propose_for_item`` treats as
    a hard patch-generation block). Safety-sensitive / critical findings still pause for approval
    regardless of this knob — only the non-safety *quality* blocks honour it.

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
    # Non-safety quality blocks are advisory unless enforcement is explicitly "block". This matches the
    # depth gate / safe-apply / autopilot convention and prevents an auto-injected fallback test_plan
    # (which the planner adds when the LLM omits one) from permanently blocking patch generation.
    enforce = str(quality_gate_enforcement or "block").lower() == "block"
    warnings: list[str] = []
    structure_findings = _plan_structure_findings(plan) if full_auto else []
    if structure_findings:
        warnings.append("plan_structure_quality_gate_blocked")
        if not enforce:
            warnings.append("plan_structure_quality_gate_warn_only")
        return {
            "critique_gate": {
                "gate_status": "blocked" if enforce else "warn",
                "reason": "plan_structure_quality_gate_blocked",
                "blocking_findings": structure_findings,
                "safety_sensitive": False,
                "enforced": enforce,
            },
            "plan_revision_required": enforce,
            "require_approval": enforce,
            "warnings": warnings,
            "clarification": {},
        }

    if not gate["blocked"]:
        return {
            "critique_gate": {"gate_status": gate["gate_status"]},
            "plan_revision_required": False,
            "require_approval": False,
            "warnings": warnings,
            "clarification": {},
        }

    blocking = gate["blocking_findings"]
    # A plan confined to the project's sandbox working folder (frontend/non-executable files, no
    # destructive or command-execution steps) has no safety blast radius, so a raw "critical"
    # severity label on a QUALITY/logic finding must not by itself force a critical safety event.
    # Genuine safety-keyword findings still escalate regardless of scope.
    sandbox_frontend_only = _plan_is_sandbox_frontend_only(plan)
    safety_sensitive = any(
        _finding_is_safety_sensitive(f, allow_severity_escalation=not sandbox_frontend_only)
        for f in blocking
    )
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

    # supervised / lower preset, non-safety high finding → block + ask for revision (when enforced).
    warnings.append("high_critique_requires_revision")
    if not enforce:
        warnings.append("high_critique_warn_only")
    return {
        "critique_gate": {
            "gate_status": "blocked" if enforce else "warn",
            "reason": "high_critique_requires_revision",
            "residual_risk": residual_risk,
            "blocking_findings": blocking,
            "safety_sensitive": False,
            "enforced": enforce,
        },
        "plan_revision_required": enforce,
        "require_approval": enforce,
        "warnings": warnings,
        "clarification": _clarification(),
    }


def _plan_structure_findings(plan: dict) -> list[dict]:
    findings: list[dict] = []
    steps = plan.get("implementation_steps")
    if isinstance(steps, list):
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            if not str(step.get("description") or "").strip():
                findings.append(_structure_finding("empty_step_description", index))
            if not _non_empty_list(step.get("acceptance_criteria")):
                findings.append(_structure_finding("empty_step_acceptance_criteria", index))
    metadata = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
    warnings = [str(w) for w in (plan.get("warnings") or []) if str(w).strip()] if isinstance(plan.get("warnings"), list) else []
    has_current_steps = isinstance(steps, list) and any(isinstance(step, dict) for step in steps)
    if (metadata.get("planner_fallback") or metadata.get("fallback_plan_items_generated") or "planner_fallback_skeleton_generated" in warnings) and not has_current_steps:
        findings.append(_structure_finding("fallback_only_plan_pool", 0))
    test_plan = plan.get("test_plan")
    fallback_tests = {"APIレスポンス構造の確認", "保存ファイル(JSON/Markdown)の存在確認"}
    if isinstance(test_plan, list) and test_plan and all(str(item) in fallback_tests for item in test_plan):
        findings.append(_structure_finding("fallback_only_test_plan", 0))
    return findings


def _non_empty_list(value) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)


def _structure_finding(code: str, step_index: int) -> dict:
    return {
        "severity": "high",
        "category": "plan_structure",
        "title": code,
        "detail": f"{code} detected" + (f" at step {step_index}" if step_index else ""),
        "recommendation": "Regenerate the plan with non-empty step descriptions, acceptance criteria, and concrete tests.",
        "code": code,
        "step_index": step_index,
    }
