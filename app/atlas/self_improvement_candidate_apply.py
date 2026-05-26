from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.atlas.candidate_workspace_manager import load_candidate_workspace_plan, validate_candidate_workspace_plan
from app.atlas.patch_transaction import read_patch_transaction_manifest
from app.atlas.self_improvement_patch_apply import (
    REQUIRED_CONFIRMATION_TEXT as INNER_APPLY_CONFIRMATION_TEXT,
    apply_self_improvement_patch_one_action,
    validate_self_improvement_patch_apply,
)

SCHEMA_VERSION = "atlas.self_improvement_candidate_apply.v1"
TRACK_PR = "PR-ATLAS-SCALE-153"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-154"
REQUIRED_CONFIRMATION_TEXT = "APPLY SELF IMPROVEMENT CANDIDATE PATCH"

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "strict": 3, "strict_gate": 3}
_REQUIRED_FALSE_FLAGS = (
    "stable_runtime_mutation_enabled",
    "stable_runtime_mutation_performed",
    "self_apply_enabled",
    "self_modification_enabled",
    "command_execution_enabled",
    "command_execution_performed",
    "verification_execution_enabled",
    "verification_performed",
    "promotion_enabled",
    "promotion_performed",
    "direct_merge_enabled",
    "remote_git_push_enabled",
    "vue_authoritative",
    "vue_execution_controls_enabled",
    "autonomous_execution_enabled",
    "autonomous_loop_execution_enabled",
    "auto_continue_enabled",
    "execute_all_enabled",
)


def apply_self_improvement_candidate_patch_one_action(
    *,
    candidate_workspace_plan_path: str | Path,
    dry_run_verification_path: str | Path,
    patch_transaction_manifest_path: str | Path,
    data_root: str | Path,
    dry_run_gate_ready: bool = False,
    rollback_ready: bool = False,
    strict_gate_approved: bool = False,
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    dry_run: bool = False,
) -> dict[str, Any]:
    plan = load_candidate_workspace_plan(manifest_path=candidate_workspace_plan_path)
    blocked = _validate_candidate_plan_for_apply(plan)
    candidate_root = Path(str(plan.get("candidate_root", ""))).expanduser().resolve()
    transaction_path = Path(patch_transaction_manifest_path).expanduser().resolve()
    transaction = _read_transaction_for_policy(data_root=data_root, transaction_path=transaction_path, blocked=blocked)
    changed_files = _changed_files(transaction)
    blocked.extend(_validate_transaction_scope(plan=plan, transaction=transaction, changed_files=changed_files))
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("candidate_confirmation_text_mismatch")

    inner_result: dict[str, Any] | None = None
    if not blocked:
        inner_result = apply_self_improvement_patch_one_action(
            dry_run_verification_path=dry_run_verification_path,
            patch_transaction_manifest_path=transaction_path,
            data_root=data_root,
            project_path=candidate_root,
            dry_run_gate_ready=dry_run_gate_ready,
            rollback_ready=rollback_ready,
            strict_gate_approved=strict_gate_approved,
            confirmation_token_present=confirmation_token_present,
            confirmation_text=INNER_APPLY_CONFIRMATION_TEXT,
            approval_status=approval_status,
            explicit_decision=explicit_decision,
            dry_run=dry_run,
        )
        validate_self_improvement_patch_apply(inner_result)
        if inner_result.get("status") == "blocked":
            blocked.extend(str(reason) for reason in inner_result.get("blocked_reasons", []))

    status = "blocked" if blocked else str(inner_result.get("status", "blocked"))
    result = {
        "schema_version": SCHEMA_VERSION,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": status,
        "blocking_reasons": list(dict.fromkeys(blocked)),
        "backend_authoritative": True,
        "candidate_workspace_plan_id": str(plan.get("workspace_plan_id", "")),
        "candidate_root": str(candidate_root),
        "target_repo": str(Path(str(plan.get("target_repo", ""))).expanduser().resolve()),
        "changed_files": changed_files if not blocked else [],
        "candidate_apply_enabled": status in {"planned", "applied"},
        "candidate_apply_performed": status == "applied",
        "candidate_workspace_mutation_performed": status == "applied",
        "inner_apply_status": str(inner_result.get("status", "not_started")) if inner_result else "not_started",
        "inner_apply_id": str(inner_result.get("apply_id", "")) if inner_result else "",
        "inner_apply_result_path": str(inner_result.get("apply_result_path", "")) if inner_result else "",
        "dry_run": dry_run,
        "single_action": True,
        "manual_only": True,
        "approval_required": True,
        "confirmation_text_required": REQUIRED_CONFIRMATION_TEXT,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "verification_execution_enabled": False,
        "verification_performed": False,
        "promotion_enabled": False,
        "promotion_performed": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
    }
    return validate_self_improvement_candidate_apply(result)


def validate_self_improvement_candidate_apply(result: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "backend_authoritative",
        "candidate_workspace_plan_id",
        "candidate_root",
        "target_repo",
        "changed_files",
        "candidate_apply_enabled",
        "candidate_apply_performed",
        "candidate_workspace_mutation_performed",
        "single_action",
        "manual_only",
        "approval_required",
        "confirmation_text_required",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in result]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    is_blocked = result.get("status") == "blocked"
    candidate_root = Path(str(result.get("candidate_root", ""))).expanduser().resolve()
    target_repo = Path(str(result.get("target_repo", ""))).expanduser().resolve()
    invariants = {
        "schema_version": result.get("schema_version") == SCHEMA_VERSION,
        "track_pr": result.get("track_pr") == TRACK_PR,
        "next_required_pr": result.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": result.get("status") in {"blocked", "planned", "applied"},
        "blocked_reasons": not is_blocked or bool(result.get("blocking_reasons")),
        "backend_authoritative": result.get("backend_authoritative") is True,
        "candidate_root_not_target_repo": candidate_root != target_repo and not _is_relative_to(candidate_root, target_repo),
        "candidate_apply_enabled": result.get("candidate_apply_enabled") is (result.get("status") in {"planned", "applied"}),
        "candidate_apply_performed": result.get("candidate_apply_performed") is (result.get("status") == "applied"),
        "candidate_workspace_mutation_performed": result.get("candidate_workspace_mutation_performed") is (result.get("status") == "applied"),
        "changed_files": result.get("status") != "applied" or bool(result.get("changed_files")),
        "single_action": result.get("single_action") is True,
        "manual_only": result.get("manual_only") is True,
        "approval_required": result.get("approval_required") is True,
        "confirmation_text_required": result.get("confirmation_text_required") == REQUIRED_CONFIRMATION_TEXT,
    }
    invariants.update({key: result.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return result


def _validate_candidate_plan_for_apply(plan: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    validate_candidate_workspace_plan(plan)
    if plan.get("status") != "ready":
        blocked.append("candidate_workspace_plan_ready_required")
    if plan.get("candidate_workspace_manager_enabled") is not True:
        blocked.append("candidate_workspace_manager_enabled_required")
    target_repo = Path(str(plan.get("target_repo", ""))).expanduser().resolve()
    candidate_root = Path(str(plan.get("candidate_root", ""))).expanduser().resolve()
    if candidate_root == target_repo or _is_relative_to(candidate_root, target_repo):
        blocked.append("candidate_root_must_not_be_stable_repo")
    return blocked


def _read_transaction_for_policy(*, data_root: str | Path, transaction_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        parsed = read_patch_transaction_manifest(manifest_path=transaction_path, data_root=data_root)
        return dict(parsed.get("manifest", {}))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"patch_transaction_read_failed:{type(exc).__name__}")
        return {}


def _changed_files(transaction: dict[str, Any]) -> list[str]:
    files = []
    for entry in transaction.get("proposed_files", []):
        rel = str(entry.get("relative_path", "")).strip().replace("\\", "/").strip("/")
        if rel:
            files.append(rel)
    return files


def _validate_transaction_scope(*, plan: dict[str, Any], transaction: dict[str, Any], changed_files: list[str]) -> list[str]:
    blocked: list[str] = []
    if not transaction:
        return blocked
    if not changed_files:
        blocked.append("changed_file_required")
    if len(changed_files) > int(plan.get("max_files", 0)):
        blocked.append("changed_file_count_exceeds_candidate_limit")
    allowed = [str(path) for path in plan.get("allowed_paths", [])]
    denied = [str(path) for path in plan.get("blocked_paths", [])]
    for rel in changed_files:
        if not _path_is_allowed(rel, allowed):
            blocked.append("changed_file_outside_candidate_allowed_paths")
        if _path_is_allowed(rel, denied):
            blocked.append("changed_file_matches_candidate_blocked_paths")
    risk = str(transaction.get("risk_class", "strict_gate"))
    max_risk = str(plan.get("max_risk_level", "low"))
    if _RISK_ORDER.get(risk, 3) > _RISK_ORDER.get(max_risk, 0):
        blocked.append("risk_class_exceeds_candidate_limit")
    return blocked


def _path_is_allowed(path: str, patterns: list[str]) -> bool:
    normalized = path.strip().replace("\\", "/").strip("/")
    for pattern in patterns:
        prefix = pattern.strip().replace("\\", "/").strip("/")
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return True
    return False


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([str(parent.resolve()), str(child.resolve())]) == str(parent.resolve())
    except ValueError:
        return False
