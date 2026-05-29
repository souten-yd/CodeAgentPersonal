from __future__ import annotations


def normalize_action_type(action_type: object) -> str:
    """Normalize an item's action_type to the canonical file-apply vocabulary.

    The file executor only applies {create, update}. Older/other pipelines used
    {write, patch} and empty. Map them so eligibility and the executor agree:
    write/empty -> create (greenfield write), patch -> update. delete/run_command
    are passed through unchanged so the forbidden-action guards still fire.
    """
    value = str(action_type or "").strip().lower()
    if value in {"create", "update", "delete", "run_command"}:
        return value
    if value == "patch":
        return "update"
    # "write", "", and any unknown value default to create.
    return "create"
