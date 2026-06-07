from __future__ import annotations


def normalize_action_type(action_type: object) -> str:
    """Normalize an item's action_type to the canonical file-apply vocabulary.

    Only explicit current or compatible legacy values are mapped. Unknown or
    empty values stay invalid so callers can fail closed instead of silently
    creating files.
    """
    value = str(action_type or "").strip().lower()
    if value in {"create", "update", "delete", "run_command"}:
        return value
    if value in {"patch", "edit", "modify"}:
        return "update"
    if value in {"write", "add"}:
        return "create"
    return ""
