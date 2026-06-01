"""Single source of truth for full-automation (full_auto) safety relaxation.

full_auto may continue non-critical quality findings, but it must not bypass critical events.
Critical risk, safety-sensitive, protected-path, data-loss, and destructive findings are normalized
into a critical-event payload and paused for an explicit user decision. Forbidden direct operations
(such as delete/run-command policy violations) remain blocked unless a separate backend gate
authorizes them.

`is_full_auto_preset` is reused from `atlas_plan_quality_gate` so the "what counts as full_auto"
decision lives in exactly one place."""

from __future__ import annotations

from agent.atlas_critical_event_policy import critical_event_from_policy_evaluation
from agent.atlas_plan_quality_gate import is_full_auto_preset  # shared single source of truth

# Categories that remain disabled unless a separate backend gate explicitly authorizes them.
FULL_AUTO_FORBIDDEN_CATEGORIES = frozenset({
    "delete_forbidden",
    "run_command_forbidden",
})

# Critical categories always require an explicit user decision under full_auto; critical_handling=auto
# is intentionally ignored for these categories.
FULL_AUTO_CRITICAL_DECISION_CATEGORIES = frozenset({
    "critical_risk",
    "protected_path",
    "security",
    "data_loss",
    "destructive_change",
})


def relax_evaluation_for_full_auto(evaluation, *, preset_id: str = "", automation_level: str = "", critical_handling: str | None = None):
    """Return a full_auto-relaxed copy of a policy-gate evaluation.

    - Non full_auto presets/levels: the evaluation is returned unchanged (backward compatible).
    - Critical categories (critical/security/data_loss/destructive/protected_path) always become
      ``require_approval`` with a ``waiting_for_critical_decision`` payload.
    - Forbidden direct operations (delete/run_command policy violations) remain ``block`` unless a
      separate backend gate authorizes them, but are still surfaced as critical events.
    - Any other ``block`` (terminal-status / generic manual_gate) is NOT relaxed — a
      failed/blocked/cancelled item is never resurrected.
    - A pure quality ``require_approval`` (high/medium/dependency/api/ui/docker/db/files/size/
      requires_user_confirmation) -> ``allow``.
    - ``allow`` is left untouched.

    The relaxed copy records ``metadata.full_auto_relaxed`` / ``full_auto_original_decision`` for
    auditability and re-syncs ``blocked`` / ``requires_user_confirmation`` / ``auto_execution_allowed``.
    """
    if not is_full_auto_preset(preset_id=preset_id, automation_level=automation_level):
        return evaluation

    categories = set(evaluation.categories or [])
    decision = evaluation.decision
    _ = critical_handling  # critical_handling=auto must not bypass critical events.
    forbidden = bool(categories & FULL_AUTO_FORBIDDEN_CATEGORIES)
    critical = bool(categories & FULL_AUTO_CRITICAL_DECISION_CATEGORIES)

    if decision == "block":
        if forbidden:
            new_decision = "block"
        elif critical:
            new_decision = "require_approval"
        else:
            # Generic / terminal-status block — never resurrected.
            new_decision = "block"
    elif decision == "require_approval":
        if forbidden:
            new_decision = "block"
        elif critical:
            new_decision = "require_approval"
        else:
            new_decision = "allow"
    else:
        new_decision = decision

    critical_event = critical_event_from_policy_evaluation(evaluation, source_gate="safe_apply_gate") if (critical or forbidden) else None
    if new_decision == decision and not critical_event:
        return evaluation

    relaxed = evaluation.model_copy(deep=True)
    relaxed.decision = new_decision
    relaxed.blocked = new_decision == "block"
    relaxed.requires_user_confirmation = new_decision == "require_approval"
    relaxed.auto_execution_allowed = new_decision == "allow"
    relaxed.metadata = dict(relaxed.metadata or {})
    relaxed.metadata["full_auto_relaxed"] = True
    relaxed.metadata["full_auto_original_decision"] = decision
    relaxed.metadata["full_auto_critical_handling"] = "user_decision_required_for_critical_events"
    if critical_event:
        relaxed.metadata["critical_event"] = critical_event
        relaxed.metadata["status"] = "waiting_for_critical_decision"
    return relaxed
