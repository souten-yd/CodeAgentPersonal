from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.patch_transaction import read_patch_transaction_manifest, validate_patch_transaction
from app.atlas.patch_transaction_apply import _apply_unified_diff, _select_single_entry
from app.atlas.self_improvement_dry_run_verification import (
    SCHEMA_VERSION as DRY_RUN_VERIFICATION_SCHEMA_VERSION,
    load_self_improvement_dry_run_verification,
)

SCHEMA_VERSION = "atlas.self_improvement_patch_apply.v1"
TRACK_PR = "PR-ATLAS-SCALE-144"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-145"
REQUIRED_CONFIRMATION_TEXT = "APPLY SELF IMPROVEMENT PATCH"
_REQUIRED_VERIFICATION_TRACK = "PR-ATLAS-SCALE-143"


def apply_self_improvement_patch_one_action(
    *,
    dry_run_verification_path: str | Path,
    patch_transaction_manifest_path: str | Path,
    data_root: str | Path,
    project_path: str | Path | None = None,
    dry_run_gate_ready: bool = False,
    rollback_ready: bool = False,
    strict_gate_approved: bool = False,
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    dry_run: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    root = Path(data_root).expanduser().resolve()
    verification_path = Path(dry_run_verification_path).expanduser().resolve()
    transaction_path = Path(patch_transaction_manifest_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, verification_path, "dry_run_verification_outside_data_root")
        _ensure_under(root, transaction_path, "patch_transaction_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    verification = load_self_improvement_dry_run_verification(manifest_path=verification_path, data_root=root)
    blocked.extend(_validate_dry_run_verification(verification))
    parsed = read_patch_transaction_manifest(manifest_path=transaction_path, data_root=root)
    transaction = parsed["manifest"]
    transaction_id = str(transaction.get("transaction_id", ""))
    transaction_dir = transaction_path.parent

    validation = validate_patch_transaction(manifest_path=transaction_path, data_root=root, project_path=project_path)
    if not validation.get("valid"):
        blocked.append("transaction_validation_failed")
    if not validation.get("snapshot_reference_valid"):
        blocked.append("snapshot_reference_required")
    if not validation.get("path_safety_valid"):
        blocked.append("path_safety_invalid")
    if not validation.get("rollback_ready") or not rollback_ready:
        blocked.append("rollback_ready_required")
    if not dry_run_gate_ready:
        blocked.append("dry_run_gate_ready_required")
    if verification.get("strict_gate_required") is True and not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    entry, entry_errors = _select_single_entry(list(transaction.get("proposed_files", [])))
    blocked.extend(entry_errors)
    if entry is not None and entry.get("change_type") not in {"create", "modify"}:
        blocked.append("create_or_modify_change_required")

    diff_text = ""
    diff_path_value = transaction.get("diff_text_path")
    if not diff_path_value:
        blocked.append("diff_text_required")
    else:
        try:
            diff_path = _ensure_under(transaction_dir, Path(diff_path_value), "diff_path_outside_transaction_dir")
            diff_text = diff_path.read_text(encoding="utf-8") if diff_path.exists() else ""
            if not diff_text:
                blocked.append("diff_text_missing")
        except ValueError as exc:
            blocked.append(str(exc))

    project_root = Path(project_path if project_path is not None else transaction.get("project_path", "")).expanduser().resolve()
    target: Path | None = None
    if entry is not None:
        try:
            target = _ensure_under(project_root, project_root / str(entry.get("relative_path", "")), "target_outside_project")
            if target.exists() and target.is_symlink():
                blocked.append("target_symlink_forbidden")
            if entry.get("change_type") == "modify" and not target.exists():
                blocked.append("modify_target_missing")
            if entry.get("change_type") == "create" and target.exists():
                blocked.append("create_target_exists")
        except ValueError as exc:
            blocked.append(str(exc))

    before = ""
    final_content: str | None = None
    if not blocked and target is not None:
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        final_content = _apply_unified_diff(before, diff_text)
        if final_content is None:
            blocked.append("diff_parse_failed")

    apply_id = _apply_id(created)
    result = _base_result(
        apply_id=apply_id,
        transaction_id=transaction_id,
        verification_id=str(verification.get("verification_id", "")),
        status="blocked" if blocked else ("planned" if dry_run else "applied"),
        blocked_reasons=list(dict.fromkeys(blocked)),
        changed_files=[str(entry.get("relative_path", ""))] if entry is not None and not blocked else [],
    )
    if blocked or dry_run:
        return validate_self_improvement_patch_apply(result)

    assert target is not None and final_content is not None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(final_content, encoding="utf-8")
    result.update({"actual_file_changed": before != final_content, "mutation_performed": before != final_content, "applied_at": _utc_now()})
    result_path = root / "atlas" / "self_improvement_patch_applies" / apply_id / "manifest.json"
    _ensure_under(root, result_path, "apply_result_outside_data_root")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    result["apply_result_path"] = str(result_path)
    return validate_self_improvement_patch_apply(result)


def validate_self_improvement_patch_apply(result: dict[str, Any]) -> dict[str, Any]:
    required_false = [
        "vue_authoritative",
        "vue_execution_controls_enabled",
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
        "verification_result_fabricated",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
    ]
    invariants = {
        "schema_version": result.get("schema_version") == SCHEMA_VERSION,
        "track_pr": result.get("track_pr") == TRACK_PR,
        "next_required_pr": result.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": result.get("status") in {"blocked", "planned", "applied"},
        "single_action": result.get("single_action") is True,
        "manual_only": result.get("manual_only") is True,
        "approval_required": result.get("approval_required") is True,
        "confirmation_text_required": result.get("confirmation_text_required") == REQUIRED_CONFIRMATION_TEXT,
        "backend_authoritative": result.get("backend_authoritative") is True,
        "blocked_reasons": result.get("status") != "blocked" or bool(result.get("blocked_reasons")),
        "changed_files": result.get("status") != "applied" or len(result.get("changed_files", [])) == 1,
    }
    invariants.update({key: result.get(key) is False for key in required_false})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return result


def _validate_dry_run_verification(verification: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if verification.get("schema_version") != DRY_RUN_VERIFICATION_SCHEMA_VERSION:
        blocked.append("unsupported_dry_run_verification_schema")
    if verification.get("track_pr") != _REQUIRED_VERIFICATION_TRACK:
        blocked.append("dry_run_verification_track_required")
    if verification.get("next_required_pr") != TRACK_PR:
        blocked.append("dry_run_verification_next_pr_required")
    if verification.get("dry_run_verification_authorized") is not True:
        blocked.append("authorized_dry_run_verification_required")
    if verification.get("self_improvement_dry_run_verification_enabled") is not True:
        blocked.append("dry_run_verification_enabled_required")
    if not verification.get("allowed_commands"):
        blocked.append("allowed_verification_command_required")
    for key in (
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
        "patch_applied",
        "verification_performed",
        "verification_result_fabricated",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
    ):
        if verification.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _base_result(*, apply_id: str, transaction_id: str, verification_id: str, status: str, blocked_reasons: list[str], changed_files: list[str]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "apply_id": apply_id,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "transaction_id": transaction_id,
        "verification_id": verification_id,
        "status": status,
        "blocked_reasons": blocked_reasons,
        "changed_files": changed_files,
        "actual_file_changed": False,
        "single_action": True,
        "manual_only": True,
        "approval_required": True,
        "confirmation_text_required": REQUIRED_CONFIRMATION_TEXT,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
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
        "verification_result_fabricated": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
        "mutation_performed": False,
    }


def _apply_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"self_improvement_patch_apply_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
