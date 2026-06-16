from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.atlas_action_type import normalize_action_type
from agent.atlas_plan_pool_schema import AtlasPlanItem


FORBIDDEN_FILE_CHANGE_ACTIONS = {
    "delete",
    "run_command",
    "execute",
    "shell",
    "external_fetch",
    "arbitrary_command",
}
ALLOWED_FILE_CHANGE_ACTIONS = {"create", "update"}
DEFAULT_CHANGE_SET = {
    "mode": "atomic",
    "apply_strategy": "preflight_all_then_apply_all",
    "partial_apply_allowed": False,
    "rollback_on_failure": False,
    "normalized_from_file_changes": True,
}
PROTECTED_PATH_PREFIXES = (".git", ".hg", ".svn")
SYSTEM_PATH_PREFIXES = (
    "etc",
    "usr",
    "bin",
    "sbin",
    "var",
    "windows",
    "program files",
    "program files (x86)",
)


def normalize_plan_item_file_changes(item: AtlasPlanItem) -> dict[str, Any]:
    """Normalize multi-file PlanItem metadata before snapshot, eligibility, and safe apply.

    This keeps PlanItem.target_files as the impact/snapshot surface while preserving
    metadata.file_changes as the canonical apply surface.
    """
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    item.metadata = metadata
    file_changes = metadata.get("file_changes")
    warnings: list[str] = []
    changed = False
    if not isinstance(file_changes, list) or not file_changes:
        return {"changed": False, "warnings": warnings, "file_change_paths": []}

    normalized_changes: list[dict[str, Any]] = []
    file_change_paths: list[str] = []
    for index, raw in enumerate(file_changes, start=1):
        if not isinstance(raw, dict):
            warnings.append("invalid_file_change")
            continue
        change = dict(raw)
        path = str(change.get("path") or "").strip().replace("\\", "/")
        action_type = str(change.get("action_type") or metadata.get("action_type") or "").strip().lower()
        action_type = normalize_action_type(action_type)
        if path:
            change["path"] = path
            file_change_paths.append(path)
        if action_type:
            change["action_type"] = action_type
        if not str(change.get("change_id") or "").strip() and path:
            change["change_id"] = f"fc_{index}_{_safe_change_id(path)}"
        if not str(change.get("content_mode") or "").strip():
            mode = infer_content_mode(change)
            if mode:
                change["content_mode"] = mode
        normalized_changes.append(change)

    if normalized_changes != file_changes:
        metadata["file_changes"] = normalized_changes
        changed = True

    existing_targets = [str(p).strip().replace("\\", "/") for p in (item.target_files or []) if str(p).strip()]
    merged_targets = list(dict.fromkeys([*existing_targets, *file_change_paths]))
    if merged_targets != list(item.target_files or []):
        item.target_files = merged_targets
        changed = True

    for target in existing_targets:
        if target not in file_change_paths:
            warnings.append("target_file_without_file_change")

    change_set = dict(metadata.get("change_set") or {})
    default_change_set = {**DEFAULT_CHANGE_SET, "change_set_id": f"cs_{item.item_id}"}
    merged_change_set = {**default_change_set, **change_set, "normalized_from_file_changes": True}
    if merged_change_set != metadata.get("change_set"):
        metadata["change_set"] = merged_change_set
        changed = True
    if warnings:
        warnings = list(dict.fromkeys(warnings))
        item.warnings = list(dict.fromkeys([*(item.warnings or []), *warnings]))
        metadata["normalization_warnings"] = list(dict.fromkeys([*(metadata.get("normalization_warnings") or []), *warnings]))
    return {"changed": changed, "warnings": list(dict.fromkeys(warnings)), "file_change_paths": file_change_paths}


def normalize_change_set(item: AtlasPlanItem) -> dict[str, Any]:
    normalize_plan_item_file_changes(item)
    return dict((item.metadata or {}).get("change_set") or {})


def normalize_file_changes(item: AtlasPlanItem) -> list[dict[str, Any]]:
    normalize_plan_item_file_changes(item)
    changes = (item.metadata or {}).get("file_changes")
    return [dict(change) for change in changes] if isinstance(changes, list) else []


def normalize_target_files_from_file_changes(item: AtlasPlanItem) -> list[str]:
    normalize_plan_item_file_changes(item)
    return list(item.target_files or [])


def extract_planned_paths(item: AtlasPlanItem) -> list[str]:
    changes = normalize_file_changes(item)
    if changes:
        return list(dict.fromkeys(str(change.get("path") or "").strip().replace("\\", "/") for change in changes if str(change.get("path") or "").strip()))
    return [str(path).strip().replace("\\", "/") for path in (item.target_files or []) if str(path).strip()]


def detect_duplicate_file_change_paths(item: AtlasPlanItem) -> list[str]:
    paths = [str(change.get("path") or "").strip().replace("\\", "/") for change in normalize_file_changes(item)]
    return sorted({path for path in paths if path and paths.count(path) > 1})


def detect_executor_readable_content(item: AtlasPlanItem) -> bool:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    patch_proposal = metadata.get("patch_proposal") if isinstance(metadata.get("patch_proposal"), dict) else {}
    top_level = (
        metadata.get("proposed_content"),
        metadata.get("patch"),
        metadata.get("unified_diff_preview"),
        metadata.get("edits"),
        metadata.get("append_content"),
        patch_proposal.get("proposed_content"),
        patch_proposal.get("patch"),
        patch_proposal.get("unified_diff_preview"),
        patch_proposal.get("edits"),
        patch_proposal.get("append_content"),
    )
    if any((isinstance(value, str) and value.strip()) or (isinstance(value, list) and value) for value in top_level):
        return True
    changes = normalize_file_changes(item)
    return bool(changes) and all(has_file_change_content(change) for change in changes)


def collect_normalization_warnings(item: AtlasPlanItem) -> list[str]:
    result = normalize_plan_item_file_changes(item)
    metadata_warnings = (item.metadata or {}).get("normalization_warnings") or []
    return list(dict.fromkeys([*list(result.get("warnings") or []), *list(metadata_warnings)]))


def infer_content_mode(change: dict[str, Any]) -> str:
    if isinstance(change.get("proposed_content"), str) and change.get("proposed_content"):
        return "full_content"
    if isinstance(change.get("patch"), str) and change.get("patch"):
        return "unified_diff"
    if isinstance(change.get("unified_diff_preview"), str) and change.get("unified_diff_preview"):
        return "unified_diff"
    if isinstance(change.get("edits"), list) and change.get("edits"):
        return "edits"
    if isinstance(change.get("append_content"), str) and change.get("append_content"):
        return "append"
    return ""


def validate_protected_relative_path(rel_path: str, *, workspace_root: Path | str | None = None) -> tuple[bool, str, Path | None]:
    value = str(rel_path or "").strip().replace("\\", "/")
    if not value:
        return False, "empty_target_path", None
    candidate = Path(value)
    lowered_parts = [str(part).strip().lower() for part in candidate.parts]
    lowered = value.lower().lstrip("/")
    if candidate.is_absolute() or _looks_like_windows_absolute(value):
        return False, "unsafe_target_path", None
    if ".." in candidate.parts:
        return False, "unsafe_target_path", None
    if lowered_parts and lowered_parts[0] in PROTECTED_PATH_PREFIXES:
        return False, "protected_path", None
    if lowered_parts and lowered_parts[0] in SYSTEM_PATH_PREFIXES:
        return False, "protected_path", None
    if lowered.startswith(("/etc/", "/usr/", "/bin/", "/sbin/", "/var/")):
        return False, "protected_path", None
    # Self-modification guardrail (opt-in via ATLAS_SELF_MODIFICATION_GUARD; off by default so ordinary
    # user projects are unaffected): an autonomous run editing this repo's OWN safety-critical control
    # modules must not silently weaken them — block until explicitly approved.
    try:
        from agent.atlas_self_modification_policy import (
            is_self_protected_path, resolve_self_modification_guard,
        )
        if resolve_self_modification_guard() and is_self_protected_path(value):
            return False, "self_protected_path", None
    except Exception:
        pass
    if workspace_root is None:
        return True, "", None
    root = Path(workspace_root).resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return False, "unsafe_target_path", None
    return True, "", resolved


def has_file_change_content(change: dict[str, Any]) -> bool:
    return bool(
        (isinstance(change.get("proposed_content"), str) and change.get("proposed_content"))
        or (isinstance(change.get("patch"), str) and change.get("patch"))
        or (isinstance(change.get("unified_diff_preview"), str) and change.get("unified_diff_preview"))
        or (isinstance(change.get("edits"), list) and change.get("edits"))
        or (isinstance(change.get("append_content"), str) and change.get("append_content"))
    )


def _looks_like_windows_absolute(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}


def _safe_change_id(path: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in path).strip("_")[:60] or "file"
