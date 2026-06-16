"""Self-modification guardrail.

When the autonomous loop edits KasaneCore *itself* (self-improvement), it must not be able to silently
weaken its OWN safety controls — Safe Apply, approval gates, the Git Steward, the critical-operation
policy, the full-auto gate, and this guardrail. Those modules are the controls that keep every other
change safe; an autonomous run that could rewrite them could disable the very boundaries it is supposed
to honor.

This module defines that protected set and a decision helper. Enforcement is **opt-in** via
``ATLAS_SELF_MODIFICATION_GUARD`` (default off, so ordinary user projects — where a path like
``agent/atlas_safe_apply_adapter.py`` is just a normal file — are unaffected). It is intended to be
turned ON for any autonomous run whose workspace is this repository. Editing a protected module is not
forbidden outright; it requires explicit human approval rather than autonomous application.

Pure and side-effect free: it classifies a path; it never applies, blocks at the FS level, or mutates.
"""
from __future__ import annotations

import os

SELF_MODIFICATION_GUARD_ENV = "ATLAS_SELF_MODIFICATION_GUARD"

# Repository-relative path prefixes of the system's own safety-critical modules. A change whose target
# equals or sits under one of these is a modification of a control surface. Forward-slash, lowercase.
SELF_PROTECTED_PREFIXES: tuple[str, ...] = (
    # Safe Apply authority (the only sanctioned write path).
    "agent/atlas_file_safe_apply_executor.py",
    "agent/atlas_safe_apply_adapter.py",
    "agent/atlas_safe_apply_adapter_schema.py",
    "agent/atlas_auto_safe_apply_service.py",
    # Approval / human-in-the-loop gates.
    "agent/atlas_approval_service.py",
    "agent/atlas_approval_gate.py",
    "agent/atlas_approval_schema.py",
    "agent/atlas_patch_approval_manager.py",
    "agent/atlas_plan_approval_manager.py",
    # Automation / full-auto gating.
    "agent/atlas_full_auto_gate.py",
    "agent/atlas_automation_gate_service.py",
    # Critical-operation policy (what is forbidden / separately gated).
    "agent/atlas_critical_event_policy.py",
    "agent/atlas_critical_handling_policy.py",
    # Path / protected-target validation (this is what enforces protected_path itself).
    "agent/atlas_plan_item_file_changes.py",
    # Remote publication authority.
    "agent/git_steward/",
    # This guardrail.
    "agent/atlas_self_modification_policy.py",
)


def resolve_self_modification_guard(value: str | None = None) -> bool:
    """Whether the self-modification guard is enforced (default OFF; enable for autonomous runs whose
    workspace is this repository). Enable with ``ATLAS_SELF_MODIFICATION_GUARD`` in {1,on,true,yes}."""
    raw = (value if value is not None else os.environ.get(SELF_MODIFICATION_GUARD_ENV, "")).strip().lower()
    return raw in {"1", "on", "true", "yes"}


def _normalize(rel_path: str) -> str:
    return str(rel_path or "").strip().replace("\\", "/").lstrip("/").lower()


def is_self_protected_path(rel_path: str) -> bool:
    """True when the repo-relative path is one of the system's own safety-critical control modules."""
    norm = _normalize(rel_path)
    if not norm:
        return False
    return any(norm == p.rstrip("/") or norm.startswith(p if p.endswith("/") else p + "/") or norm == p
               for p in SELF_PROTECTED_PREFIXES)


def classify_self_modification(rel_path: str, *, approved: bool = False, guard_enabled: bool | None = None) -> dict:
    """Classify a change to ``rel_path``.

    Returns ``{"protected": bool, "requires_approval": bool, "allowed_without_approval": bool,
    "reason": str}``. A protected module may still be changed WITH explicit approval; what is blocked is
    *autonomous* (unapproved) modification of a control surface."""
    enabled = resolve_self_modification_guard() if guard_enabled is None else guard_enabled
    protected = enabled and is_self_protected_path(rel_path)
    if not protected:
        return {"protected": False, "requires_approval": False, "allowed_without_approval": True, "reason": ""}
    if approved:
        return {"protected": True, "requires_approval": True, "allowed_without_approval": True,
                "reason": "self_protected_path_approved"}
    return {"protected": True, "requires_approval": True, "allowed_without_approval": False,
            "reason": "self_protected_path_requires_approval"}
