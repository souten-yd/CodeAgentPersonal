from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


CRITICAL_CATEGORIES = frozenset({
    "critical_risk",
    "security",
    "data_loss",
    "destructive_change",
    "protected_path",
    "delete_forbidden",
    "run_command_forbidden",
    "self_modification",
    "stable_runtime_mutation",
    "direct_merge",
    "remote_push",
    "self_apply",
    "unbounded_automation",
    "scope_exceeded",
})

_FORBIDDEN_WITHOUT_SEPARATE_GATE = frozenset({
    "delete_forbidden",
    "run_command_forbidden",
    "direct_merge",
    "remote_push",
    "self_apply",
    "stable_runtime_mutation",
    "unbounded_automation",
})

_OPTIONS = [
    "Approve with explicit consent",
    "Reject / NG and request safer alternative",
    "Cancel",
    "Edit requirement / scope",
]


def is_critical_category(category: str) -> bool:
    return str(category or "").strip().lower() in CRITICAL_CATEGORIES


def is_separately_gated_forbidden_category(category: str) -> bool:
    return str(category or "").strip().lower() in _FORBIDDEN_WITHOUT_SEPARATE_GATE


def has_critical_categories(categories: list[str] | tuple[str, ...] | set[str]) -> bool:
    return any(is_critical_category(category) for category in categories or [])


def normalize_critical_event(
    *,
    category: str = "critical_event",
    severity: str = "critical",
    reason: str = "Critical event detected",
    affected_files: list[str] | None = None,
    affected_capabilities: list[str] | None = None,
    estimated_impact: str = "Requires explicit user judgment before continuing.",
    recommended_decision: str = "Reject / NG and request safer alternative unless this exact scope is intended.",
    safer_alternatives: list[str] | None = None,
    source_gate: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the common Atlas critical-event payload used by every gate.

    The payload is deliberately plain dict data so existing Pydantic models can carry it in
    metadata without cross-layer schema migrations.
    """
    payload: dict[str, Any] = {
        "critical_event": True,
        "category": str(category or "critical_event"),
        "severity": str(severity or "critical"),
        "reason": str(reason or "Critical event detected"),
        "affected_files": list(affected_files or []),
        "affected_capabilities": list(affected_capabilities or []),
        "estimated_impact": str(estimated_impact or "Requires explicit user judgment before continuing."),
        "recommended_decision": str(recommended_decision or "Reject / NG and request safer alternative"),
        "safer_alternatives": list(safer_alternatives or default_safer_alternatives(category)),
        "required_options": list(_OPTIONS),
        "status": "waiting_for_critical_decision",
        "source_gate": str(source_gate or ""),
        "created_at": _utc_now_iso(),
    }
    if extra:
        payload.update(dict(extra))
    return payload


def default_safer_alternatives(category: str = "") -> list[str]:
    category = str(category or "critical_event").lower()
    alternatives = [
        "Reduce file scope to the minimum reviewed files.",
        "Use a proposal-only or dry-run-only plan before mutating files.",
        "Split the work into bounded manual steps with verification after each step.",
    ]
    if "security" in category:
        alternatives.append("Prefer validation, tests, or documentation before changing auth/security behavior.")
    if "data_loss" in category or "destructive" in category or "delete" in category:
        alternatives.append("Avoid deletion or destructive mutation; create a reversible backup/snapshot path instead.")
    if "runtime" in category or "run_command" in category or "unbounded" in category:
        alternatives.append("Replace automation with an allowlisted command or manual instruction.")
    return alternatives


def critical_event_from_policy_evaluation(evaluation: Any, *, source_gate: str) -> dict[str, Any] | None:
    categories = [str(c) for c in (getattr(evaluation, "categories", None) or [])]
    critical_categories = [c for c in categories if is_critical_category(c)]
    if not critical_categories:
        return None
    affected_files = list((getattr(evaluation, "metadata", {}) or {}).get("affected_files") or [])
    reason_parts = list(getattr(evaluation, "reasons", None) or [])
    reason = "; ".join(str(part) for part in reason_parts if part) or "Critical policy finding requires user decision"
    return normalize_critical_event(
        category=critical_categories[0],
        severity="critical" if "critical_risk" in critical_categories else "high",
        reason=reason,
        affected_files=affected_files,
        affected_capabilities=critical_categories,
        estimated_impact="May affect safety, protected data, runtime behavior, or irreversible operations.",
        source_gate=source_gate,
    )


def lower_impact_alternative_plan(original: dict[str, Any] | None, critical_event: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a conservative lower-impact replanning payload after user NG/rejects.

    This does not execute anything; callers must re-run critique/safety gates on the returned plan.
    """
    original = dict(original or {})
    event = dict(critical_event or {})
    reduced = {
        **original,
        "status": "needs_revision",
        "risk_level": "medium" if str(original.get("risk_level") or "").lower() in {"high", "critical"} else original.get("risk_level", "medium"),
        "requires_user_confirmation": True,
        "auto_execution_allowed": False,
        "target_files": list(original.get("target_files") or [])[:1],
        "test_commands": [],
        "metadata": {
            **dict(original.get("metadata") or {}),
            "original_critical_path_rejected": True,
            "lower_impact_alternative": True,
            "risk_reduced": [
                "file_scope",
                "mutation_scope",
                "execution_autonomy",
                "irreversible_change_risk",
            ],
            "remaining_risk": "requires_gate_rerun",
            "critical_event_summary": event,
        },
    }
    reduced["expected_changes"] = [
        "Generate a proposal-only lower-impact alternative instead of applying the original critical action.",
        "Re-run critique and safety gates before any continuation.",
    ]
    return reduced
