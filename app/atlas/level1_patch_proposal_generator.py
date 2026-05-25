from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.level1_patch_proposal.v1"
PROPOSAL_PR = "PR-ATLAS-SCALE-128"
RUNTIME_LEVEL = "level_1_guarded_single_step"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-129"

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "venv_sys",
    "tts_envs",
    "models",
    ".cache",
    "ca_data",
}


def create_level1_patch_proposal(
    *,
    project_path: str | Path,
    data_root: str | Path | None = None,
    requirement: str,
    proposed_changes: list[dict[str, Any]] | None = None,
    workspace_id: str = "default",
    pool_id: str = "",
    item_id: str = "",
    run_id: str = "",
    proposal_title: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root
    changes = [_normalize_change(project_root, item) for item in list(proposed_changes or [])]
    warnings: list[str] = []
    if not _safe_text(requirement):
        warnings.append("requirement_missing")
    if not changes:
        warnings.append("proposed_changes_missing")
    if any(not item["path_valid"] for item in changes):
        warnings.append("invalid_target_path_present")

    proposal = {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": _proposal_id(run_id=run_id, created_at=created),
        "created_at": created,
        "proposal_pr": PROPOSAL_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "workspace_id": _safe_text(workspace_id, "default"),
        "pool_id": _safe_text(pool_id),
        "item_id": _safe_text(item_id),
        "run_id": _safe_text(run_id, "run"),
        "project_path": str(project_root),
        "data_root": str(root),
        "runtime_level": RUNTIME_LEVEL,
        "proposal_title": _safe_text(proposal_title, "Patch proposal"),
        "requirement": _safe_text(requirement),
        "proposal_mode": "metadata_only_patch_proposal",
        "proposal_status": "proposal_ready" if changes and not warnings else "proposal_needs_review",
        "proposed_changes": changes,
        "target_file_count": len(changes),
        "valid_target_file_count": sum(1 for item in changes if item["path_valid"]),
        "proposal_generated": True,
        "patch_text_generated": False,
        "diff_generated": False,
        "patch_transaction_created": False,
        "patch_apply_enabled": False,
        "safe_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_safe_apply_enabled": False,
        "execution_enabled": False,
        "autonomous_execution_enabled": False,
        "remote_git_operations_enabled": False,
        "public_route_added": False,
        "vue_authoritative": False,
        "backend_authoritative": True,
        "manual_review_required": True,
        "dry_run_required_before_transaction": True,
        "explicit_approval_required_before_apply": True,
        "warnings": sorted(set(warnings)),
        "policy_notes": [
            "scale_128_patch_proposal_metadata_only",
            "no_diff_or_patch_text_generated",
            "no_patch_transaction_created_until_scale_129",
            "no_apply_or_safe_apply",
            "backend_authoritative",
        ],
    }
    return validate_level1_patch_proposal(proposal)


def validate_level1_patch_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "proposal_pr",
        "next_required_pr",
        "runtime_level",
        "proposal_mode",
        "requirement",
        "proposed_changes",
        "proposal_generated",
        "patch_text_generated",
        "diff_generated",
        "patch_transaction_created",
        "patch_apply_enabled",
        "safe_apply_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_safe_apply_enabled",
        "execution_enabled",
        "autonomous_execution_enabled",
        "remote_git_operations_enabled",
        "public_route_added",
        "vue_authoritative",
        "backend_authoritative",
        "manual_review_required",
    ]
    missing = [field for field in required if field not in proposal]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    invariants = {
        "schema_version": proposal.get("schema_version") == SCHEMA_VERSION,
        "proposal_pr": proposal.get("proposal_pr") == PROPOSAL_PR,
        "next_required_pr": proposal.get("next_required_pr") == NEXT_REQUIRED_PR,
        "runtime_level": proposal.get("runtime_level") == RUNTIME_LEVEL,
        "proposal_mode": proposal.get("proposal_mode") == "metadata_only_patch_proposal",
        "proposal_generated": proposal.get("proposal_generated") is True,
        "patch_text_generated": proposal.get("patch_text_generated") is False,
        "diff_generated": proposal.get("diff_generated") is False,
        "patch_transaction_created": proposal.get("patch_transaction_created") is False,
        "patch_apply_enabled": proposal.get("patch_apply_enabled") is False,
        "safe_apply_enabled": proposal.get("safe_apply_enabled") is False,
        "automatic_patch_generation_enabled": proposal.get("automatic_patch_generation_enabled") is False,
        "automatic_patch_apply_enabled": proposal.get("automatic_patch_apply_enabled") is False,
        "automatic_safe_apply_enabled": proposal.get("automatic_safe_apply_enabled") is False,
        "execution_enabled": proposal.get("execution_enabled") is False,
        "autonomous_execution_enabled": proposal.get("autonomous_execution_enabled") is False,
        "remote_git_operations_enabled": proposal.get("remote_git_operations_enabled") is False,
        "public_route_added": proposal.get("public_route_added") is False,
        "vue_authoritative": proposal.get("vue_authoritative") is False,
        "backend_authoritative": proposal.get("backend_authoritative") is True,
        "manual_review_required": proposal.get("manual_review_required") is True,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")

    for forbidden in ("diff_text", "patch_text", "generated_patch", "apply_result"):
        if forbidden in proposal:
            raise ValueError(f"forbidden_field:{forbidden}")
    return proposal


def write_level1_patch_proposal(*, data_root: str | Path, proposal: dict[str, Any]) -> Path:
    validated = validate_level1_patch_proposal(proposal)
    root = Path(data_root).expanduser().resolve()
    proposal_id = str(validated["proposal_id"])
    path = root / "atlas" / "patch_proposals" / proposal_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_level1_patch_proposal(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_level1_patch_proposal(json.loads(path.read_text(encoding="utf-8")))


def _normalize_change(project_root: Path, item: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    relative_path = _safe_relpath(str(item.get("relative_path", "") or ""), warnings)
    change_type = str(item.get("change_type", "modify") or "modify")
    if change_type not in {"create", "modify", "delete", "rename", "unknown"}:
        warnings.append("change_type_unknown")
        change_type = "unknown"
    path_valid = bool(relative_path)
    exists_before = False
    if relative_path:
        top = relative_path.split("/", 1)[0]
        if top in DEFAULT_EXCLUDED_DIRS:
            warnings.append("excluded_path")
            path_valid = False
        target = project_root / relative_path
        try:
            _ensure_under(project_root, target, "project_escape")
            exists_before = target.exists()
            if target.exists() and target.is_symlink():
                warnings.append("symlink_path_skipped")
                path_valid = False
        except ValueError as exc:
            warnings.append(str(exc))
            path_valid = False
    return {
        "relative_path": relative_path,
        "change_type": change_type,
        "rationale": _safe_text(item.get("rationale", "")),
        "acceptance_criteria": _safe_text(item.get("acceptance_criteria", "")),
        "risk_level": _safe_text(item.get("risk_level", "unknown"), "unknown"),
        "exists_before": exists_before,
        "path_valid": path_valid,
        "warnings": sorted(set(warnings)),
    }


def _safe_relpath(value: str, warnings: list[str]) -> str:
    text = value.strip().replace("\\", "/")
    if not text:
        warnings.append("relative_path_missing")
        return ""
    path = Path(text)
    if path.is_absolute():
        warnings.append("absolute_paths_forbidden")
        return ""
    if any(part in ("", ".", "..") for part in path.parts):
        warnings.append("path_traversal_forbidden")
        return ""
    return path.as_posix()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _proposal_id(*, run_id: str, created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"patch_proposal_{_safe_text(run_id, 'run')}_{created_norm}_{uuid.uuid4().hex[:8]}"


def _safe_text(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text[:1000]
    return fallback


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
