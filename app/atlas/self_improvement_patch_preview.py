from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.self_modification_risk_classifier import (
    SCHEMA_VERSION as RISK_CLASSIFICATION_SCHEMA_VERSION,
    load_self_modification_risk_classification,
)

SCHEMA_VERSION = "atlas.self_improvement_patch_preview.v1"
TRACK_PR = "PR-ATLAS-SCALE-142"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-143"
_MAX_PREVIEW_FILES = 5
_ALLOWED_CHANGE_TYPES = {"create", "modify", "delete", "rename"}
_REQUIRED_CLASSIFIER_TRACK = "PR-ATLAS-SCALE-141"


def create_self_improvement_patch_preview(
    *,
    classification_path: str | Path,
    proposed_changes: list[dict[str, Any]],
    summary: str,
    data_root: str | Path | None = None,
    reviewer: str = "atlas",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    classification = load_self_modification_risk_classification(manifest_path=classification_path, data_root=data_root)
    path = Path(classification_path).expanduser().resolve()
    root = Path(data_root if data_root is not None else path.parent).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, path, "classification_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_classification(classification))
    normalized_changes, change_warnings = _normalize_changes(proposed_changes)
    blocked.extend(change_warnings)
    if not summary.strip():
        blocked.append("summary_required")
    if not normalized_changes:
        blocked.append("proposed_changes_required")
    if len(normalized_changes) > _MAX_PREVIEW_FILES:
        blocked.append("too_many_preview_files")

    preview_authorized = not blocked
    preview = {
        "schema_version": SCHEMA_VERSION,
        "preview_id": _preview_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "classification_path": str(path),
        "data_root": str(root),
        "reviewer": reviewer,
        "target_repo": classification.get("target_repo", ""),
        "target_area": classification.get("target_area", ""),
        "risk_classification": classification.get("classification", ""),
        "strict_gate_required": classification.get("strict_gate_required") is True,
        "summary": summary.strip(),
        "proposed_changes": normalized_changes,
        "preview_authorized": preview_authorized,
        "preview_blocked": not preview_authorized,
        "blocking_reasons": sorted(set(blocked)),
        "self_improvement_patch_preview_enabled": preview_authorized,
        "preview_only": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "allowed_preview_actions": ["read_classification", "record_preview", "record_changed_paths", "request_human_review"],
        "forbidden_preview_actions": [
            "generate_patch",
            "apply_patch",
            "run_verification",
            "create_branch",
            "push_branch",
            "create_pr",
            "update_pr",
            "direct_merge",
            "self_apply",
            "self_modify",
            "auto_continue",
            "execute_all",
        ],
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_previewed": preview_authorized,
        "patch_applied": False,
        "verification_performed": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    return validate_self_improvement_patch_preview(preview)


def validate_self_improvement_patch_preview(preview: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "target_repo",
        "target_area",
        "risk_classification",
        "strict_gate_required",
        "summary",
        "proposed_changes",
        "preview_authorized",
        "preview_blocked",
        "self_improvement_patch_preview_enabled",
        "preview_only",
        "backend_authoritative",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "self_modification_enabled",
        "self_apply_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_previewed",
        "patch_applied",
        "verification_performed",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
    ]
    missing = [field for field in required if field not in preview]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    authorized = bool(preview.get("preview_authorized"))
    proposed_changes = list(preview.get("proposed_changes", []))
    invariants = {
        "schema_version": preview.get("schema_version") == SCHEMA_VERSION,
        "track_pr": preview.get("track_pr") == TRACK_PR,
        "next_required_pr": preview.get("next_required_pr") == NEXT_REQUIRED_PR,
        "preview_blocked": preview.get("preview_blocked") is (not authorized),
        "self_improvement_patch_preview_enabled": preview.get("self_improvement_patch_preview_enabled") is authorized,
        "preview_only": preview.get("preview_only") is True,
        "proposed_changes": (not authorized) or (0 < len(proposed_changes) <= _MAX_PREVIEW_FILES),
        "backend_authoritative": preview.get("backend_authoritative") is True,
        "vue_authoritative": preview.get("vue_authoritative") is False,
        "vue_execution_controls_enabled": preview.get("vue_execution_controls_enabled") is False,
        "self_modification_enabled": preview.get("self_modification_enabled") is False,
        "self_apply_enabled": preview.get("self_apply_enabled") is False,
        "automatic_patch_generation_enabled": preview.get("automatic_patch_generation_enabled") is False,
        "automatic_patch_apply_enabled": preview.get("automatic_patch_apply_enabled") is False,
        "automatic_verification_enabled": preview.get("automatic_verification_enabled") is False,
        "autonomous_execution_enabled": preview.get("autonomous_execution_enabled") is False,
        "autonomous_loop_execution_enabled": preview.get("autonomous_loop_execution_enabled") is False,
        "auto_continue_enabled": preview.get("auto_continue_enabled") is False,
        "execute_all_enabled": preview.get("execute_all_enabled") is False,
        "direct_merge_enabled": preview.get("direct_merge_enabled") is False,
        "remote_git_push_enabled": preview.get("remote_git_push_enabled") is False,
        "execution_performed": preview.get("execution_performed") is False,
        "mutation_performed": preview.get("mutation_performed") is False,
        "patch_generated": preview.get("patch_generated") is False,
        "patch_previewed": preview.get("patch_previewed") is authorized,
        "patch_applied": preview.get("patch_applied") is False,
        "verification_performed": preview.get("verification_performed") is False,
        "branch_created": preview.get("branch_created") is False,
        "draft_pr_created": preview.get("draft_pr_created") is False,
        "draft_pr_updated": preview.get("draft_pr_updated") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return preview


def write_self_improvement_patch_preview(*, data_root: str | Path, preview: dict[str, Any]) -> Path:
    validated = validate_self_improvement_patch_preview(preview)
    root = Path(data_root).expanduser().resolve()
    preview_id = str(validated["preview_id"])
    path = root / "atlas" / "self_improvement_patch_previews" / preview_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_self_improvement_patch_preview(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_self_improvement_patch_preview(json.loads(path.read_text(encoding="utf-8")))


def _validate_classification(classification: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if classification.get("schema_version") != RISK_CLASSIFICATION_SCHEMA_VERSION:
        blocked.append("unsupported_risk_classification_schema")
    if classification.get("track_pr") != _REQUIRED_CLASSIFIER_TRACK:
        blocked.append("risk_classification_track_required")
    if classification.get("next_required_pr") != TRACK_PR:
        blocked.append("risk_classification_next_pr_required")
    if classification.get("classification_authorized") is not True:
        blocked.append("authorized_risk_classification_required")
    if classification.get("strict_self_modification_risk_classifier_enabled") is not True:
        blocked.append("risk_classifier_enabled_required")
    for key in (
        "self_modification_enabled",
        "self_apply_enabled",
        "patch_preview_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_previewed",
        "patch_applied",
        "verification_performed",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
    ):
        if classification.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _normalize_changes(changes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, change in enumerate(changes):
        rel = str(change.get("relative_path", "") or "")
        change_type = str(change.get("change_type", "") or "")
        rationale = str(change.get("rationale", "") or "").strip()
        try:
            safe_rel = _safe_relpath(rel)
        except ValueError as exc:
            warnings.append(f"change_{index}_{exc}")
            continue
        if change_type not in _ALLOWED_CHANGE_TYPES:
            warnings.append(f"change_{index}_change_type_not_allowed")
            continue
        if not rationale:
            warnings.append(f"change_{index}_rationale_required")
            continue
        normalized.append({
            "relative_path": safe_rel,
            "change_type": change_type,
            "rationale": rationale,
            "preview_only": True,
            "content_included": False,
            "diff_included": False,
            "patch_generated": False,
            "patch_applied": False,
        })
    return normalized, warnings


def _safe_relpath(value: str) -> str:
    if not value:
        raise ValueError("empty_path_forbidden")
    path = Path(value)
    if path.is_absolute():
        raise ValueError("absolute_paths_forbidden")
    if any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("path_traversal_forbidden")
    return path.as_posix()


def _preview_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"self_improvement_patch_preview_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
