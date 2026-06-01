"""Single source of truth for full-automation (full_auto) safety relaxation.

The autonomous dev profile (`autonomous_dev_agent` / preset `autonomous_bounded_dev` /
multi-item policy `full_auto_multi_item_v1`) opts into autonomous code generation. Several
gates historically each re-derived "is this full_auto?" with ad-hoc string checks
(`preset_id == "full_auto" and risk in {"medium", "high"}`), which left gaps (the patch
metadata branch had no bypass; a low-risk item carrying `requires_user_confirmation` was not
bypassed) and scattered the policy across three layers.

This module centralizes the rule: under full_auto, a raw policy-gate evaluation is relaxed so
that only *true safety* findings still stop autonomous apply. Everything that is a quality
gate (high/medium risk, dependency/api/ui/docker/db changes, security, large patch, file count,
`requires_user_confirmation`) is allowed without approval. The compensating controls are the
plan-time critique gate (`atlas_plan_quality_gate._SAFETY_SENSITIVE_KEYWORDS`, which blocks
safety-sensitive findings before a plan is ever approved) and the pre-apply change snapshot +
rollback (`AtlasChangeSnapshotService` / `AtlasFileSafeApplyExecutor`).

`is_full_auto_preset` is reused from `atlas_plan_quality_gate` so the "what counts as full_auto"
decision lives in exactly one place.
"""

from __future__ import annotations

from agent.atlas_plan_quality_gate import is_full_auto_preset  # shared single source of truth

# Categories that ALWAYS stop autonomous apply, even under full_auto. These are structural /
# forbidden-operation invariants, not quality gates.
FULL_AUTO_HARD_BLOCK_CATEGORIES = frozenset({
    "critical_risk",
    "delete_forbidden",
    "run_command_forbidden",
})

# Categories that keep requiring human approval even under full_auto. Writing into protected
# paths (.git / ca_data / models / venv ...) stays gated by user decision.
FULL_AUTO_KEEP_APPROVAL_CATEGORIES = frozenset({
    "protected_path",
})

# Block-producing categories that full_auto is allowed to downgrade to "allow". The user opted
# into maximum autonomy (data-loss changes are reversible via the pre-apply snapshot/rollback).
# A terminal-status block surfaces as the generic "manual_gate" category and is deliberately NOT
# listed here, so a failed/blocked/cancelled item is never resurrected by the relaxation.
FULL_AUTO_RELAXABLE_BLOCK_CATEGORIES = frozenset({
    "data_loss",
})


def relax_evaluation_for_full_auto(evaluation, *, preset_id: str = "", automation_level: str = ""):
    """Return a full_auto-relaxed copy of a policy-gate evaluation.

    - Non full_auto presets/levels: the evaluation is returned unchanged (backward compatible).
    - ``block`` whose driving categories are relaxable (e.g. ``data_loss``) and not a hard block
      -> ``allow``. Any other block (critical/delete/run_command/terminal-status) stays ``block``.
    - ``require_approval`` -> ``allow`` unless it carries a keep-approval category
      (``protected_path``) or a hard-block category.
    - ``allow`` is left untouched.

    The relaxed copy records ``metadata.full_auto_relaxed`` / ``full_auto_original_decision`` for
    auditability and re-syncs ``blocked`` / ``requires_user_confirmation`` / ``auto_execution_allowed``.
    """
    if not is_full_auto_preset(preset_id=preset_id, automation_level=automation_level):
        return evaluation

    categories = set(evaluation.categories or [])
    decision = evaluation.decision

    if decision == "block":
        if (categories & FULL_AUTO_RELAXABLE_BLOCK_CATEGORIES) and not (categories & FULL_AUTO_HARD_BLOCK_CATEGORIES):
            new_decision = "allow"
        else:
            new_decision = "block"
    elif decision == "require_approval":
        if categories & FULL_AUTO_HARD_BLOCK_CATEGORIES:
            new_decision = "block"
        elif categories & FULL_AUTO_KEEP_APPROVAL_CATEGORIES:
            new_decision = "require_approval"
        else:
            new_decision = "allow"
    else:
        new_decision = decision

    if new_decision == decision:
        return evaluation

    relaxed = evaluation.model_copy(deep=True)
    relaxed.decision = new_decision
    relaxed.blocked = new_decision == "block"
    relaxed.requires_user_confirmation = new_decision == "require_approval"
    relaxed.auto_execution_allowed = new_decision == "allow"
    relaxed.metadata = dict(relaxed.metadata or {})
    relaxed.metadata["full_auto_relaxed"] = True
    relaxed.metadata["full_auto_original_decision"] = decision
    return relaxed
