from __future__ import annotations

from agent.atlas_plan_pool_schema import AtlasPlanItem

# item_type values that are never patchable (file mutations are not their purpose)
_NON_PATCH_ITEM_TYPES = frozenset({"research", "planning", "verification", "nexus_save"})

# item_type string fragments that indicate clarification/manual intent
_CLARIFICATION_TYPE_FRAGMENTS = frozenset({
    "clarification", "clarify", "manual_confirmation", "manual_confirm", "inspect",
    "ask_user", "ask-user",
})

# action_type values that are never safe-apply patchable
_FORBIDDEN_ACTION_TYPES = frozenset({"delete", "run_command", "execute", "shell"})

# Patch content keys that satisfy the "content available" requirement
_PATCH_CONTENT_KEYS = ("proposed_content", "patch", "unified_diff_preview", "edits", "append_content")


def classify_plan_item_patchability(item: AtlasPlanItem) -> dict:
    """Return {patchable: bool, reason: str} for a plan item before Safe Apply.

    This gate runs BEFORE the executor so that non-patch PlanItems (clarification,
    research, manual confirmation, etc.) are rejected at classification time rather
    than after the forbidden_action_type check in the executor.
    """
    item_type = str(item.item_type or "").strip().lower()
    action_type = str((item.metadata or {}).get("action_type") or "").strip().lower()
    metadata = item.metadata or {}

    # 1. Explicitly non-patch item types
    if item_type in _NON_PATCH_ITEM_TYPES:
        return {"patchable": False, "reason": "non_patch_plan_item"}

    # 2. Clarification-like item types (catch freeform strings from planners)
    if any(frag in item_type for frag in _CLARIFICATION_TYPE_FRAGMENTS):
        return {"patchable": False, "reason": "non_patch_plan_item"}

    # 3. run_command / forbidden action — regardless of purpose
    if action_type in _FORBIDDEN_ACTION_TYPES:
        return {"patchable": False, "reason": "run_command_clarification" if action_type == "run_command" else "forbidden_action_type"}

    # 4. implementation/documentation items must have at least one concrete target
    is_implementation = item_type in {"implementation", "documentation"}
    if is_implementation:
        has_target_files = bool(item.target_files)
        file_changes = metadata.get("file_changes")
        has_file_changes = isinstance(file_changes, list) and bool(file_changes)
        if not has_target_files and not has_file_changes:
            return {"patchable": False, "reason": "no_concrete_target"}

    # 5. Patch content must be present (skip for multi-file: each change checked at preflight)
    file_changes = metadata.get("file_changes")
    has_multi_file = isinstance(file_changes, list) and bool(file_changes)
    if not has_multi_file and is_implementation:
        has_content = _has_single_file_patch_content(metadata)
        if not has_content:
            return {"patchable": False, "reason": "patch_content_missing"}

    return {"patchable": True, "reason": ""}


def _has_single_file_patch_content(metadata: dict) -> bool:
    patch_proposal = metadata.get("patch_proposal") if isinstance(metadata.get("patch_proposal"), dict) else {}
    proposal_metadata = patch_proposal.get("metadata") if isinstance(patch_proposal.get("metadata"), dict) else {}
    # A verified already-satisfied no-op (see AtlasPatchProposalService.
    # _mark_already_satisfied_if_verified) legitimately carries none of the keys below -- there is
    # nothing to patch, the goal is already met by the file's existing content. Same exemption as
    # detect_executor_readable_content() in atlas_plan_item_file_changes.py; this is a distinct
    # duplicate "has content" check on the same item, hit one step later in the safe-apply pipeline.
    if metadata.get("already_satisfied_no_op") or proposal_metadata.get("already_satisfied_no_op"):
        return True
    for key in _PATCH_CONTENT_KEYS:
        val = metadata.get(key) or (patch_proposal.get(key) if isinstance(patch_proposal, dict) else None)
        if key == "edits":
            if isinstance(val, list) and val:
                return True
        elif isinstance(val, str) and val:
            return True
    return False
