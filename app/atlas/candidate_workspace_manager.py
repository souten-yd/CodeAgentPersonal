from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.candidate_workspace_manager.v1"
TRACK_PR = "PR-ATLAS-SCALE-149"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-150"
CURRENT_RUNTIME_LEVEL = "level_4_self_improvement_platform"

STRATEGY_GIT_WORKTREE = "git_worktree"
STRATEGY_COPY_FALLBACK = "copy_fallback"
STRATEGIES = {STRATEGY_GIT_WORKTREE, STRATEGY_COPY_FALLBACK}
RISK_LEVELS = {"low", "medium", "high", "strict"}
SELF_IMPROVEMENT_SCOPES = {
    "docs_tests_only",
    "atlas_non_runtime",
    "atlas_runtime_strict",
    "full_platform_strict",
}
_REQUIRED_FALSE_FLAGS = (
    "candidate_workspace_created",
    "stable_runtime_mutation_enabled",
    "stable_runtime_mutation_performed",
    "command_execution_enabled",
    "command_execution_performed",
    "git_worktree_execution_enabled",
    "copy_execution_enabled",
    "patch_apply_enabled",
    "patch_apply_performed",
    "verification_execution_enabled",
    "verification_performed",
    "promotion_enabled",
    "promotion_performed",
    "direct_merge_enabled",
    "remote_git_push_enabled",
    "self_apply_enabled",
    "self_modification_enabled",
    "vue_authoritative",
)


def create_candidate_workspace_plan(
    *,
    target_repo: str | Path,
    candidate_root: str | Path,
    allowed_paths: list[str],
    blocked_paths: list[str],
    stable_checkpoint_id: str,
    max_files: int,
    max_risk_level: str,
    self_improvement_scope: str,
    workspace_strategy: str = STRATEGY_GIT_WORKTREE,
    fallback_strategy: str = STRATEGY_COPY_FALLBACK,
    recovery_manifest_path: str | Path | None = None,
    safety_profile_id: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    repo = Path(target_repo).expanduser().resolve()
    root = Path(candidate_root).expanduser().resolve()
    recovery_path = str(Path(recovery_manifest_path).expanduser().resolve()) if recovery_manifest_path else ""
    blocked: list[str] = []

    if not stable_checkpoint_id:
        blocked.append("stable_checkpoint_id_required")
    if workspace_strategy not in STRATEGIES:
        blocked.append("workspace_strategy_not_allowed")
    if fallback_strategy not in STRATEGIES:
        blocked.append("fallback_strategy_not_allowed")
    if max_files < 1:
        blocked.append("max_files_must_be_positive")
    if max_risk_level not in RISK_LEVELS:
        blocked.append("max_risk_level_not_allowed")
    if self_improvement_scope not in SELF_IMPROVEMENT_SCOPES:
        blocked.append("self_improvement_scope_not_allowed")
    if not allowed_paths:
        blocked.append("allowed_paths_required")
    blocked.extend(_validate_path_patterns("allowed_path", allowed_paths))
    blocked.extend(_validate_path_patterns("blocked_path", blocked_paths))
    overlap = sorted(set(_normalize_pattern(path) for path in allowed_paths) & set(_normalize_pattern(path) for path in blocked_paths))
    if overlap:
        blocked.append("allowed_and_blocked_path_overlap")
    if root == repo or _is_relative_to(root, repo):
        blocked.append("candidate_root_must_not_be_inside_target_repo")

    plan = {
        "schema_version": SCHEMA_VERSION,
        "workspace_plan_id": _workspace_plan_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": "ready" if not blocked else "blocked",
        "blocking_reasons": sorted(set(blocked)),
        "runtime_level": CURRENT_RUNTIME_LEVEL,
        "candidate_workspace_manager_enabled": not blocked,
        "backend_authoritative": True,
        "target_repo": str(repo),
        "candidate_root": str(root),
        "workspace_strategy": workspace_strategy,
        "fallback_strategy": fallback_strategy,
        "stable_checkpoint_required": True,
        "stable_checkpoint_id": stable_checkpoint_id,
        "recovery_manifest_required": True,
        "recovery_manifest_path": recovery_path,
        "safety_profile_required": True,
        "safety_profile_id": safety_profile_id,
        "self_improvement_scope": self_improvement_scope,
        "allowed_paths": [_normalize_pattern(path) for path in allowed_paths],
        "blocked_paths": [_normalize_pattern(path) for path in blocked_paths],
        "max_files": max_files,
        "max_risk_level": max_risk_level,
        "candidate_workspace_created": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "git_worktree_execution_enabled": False,
        "copy_execution_enabled": False,
        "patch_apply_enabled": False,
        "patch_apply_performed": False,
        "verification_execution_enabled": False,
        "verification_performed": False,
        "promotion_enabled": False,
        "promotion_performed": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
        "vue_authoritative": False,
        "allowed_next_actions": [
            "review_candidate_workspace_plan",
            "record_stable_checkpoint_reference",
            "record_recovery_manifest_reference",
        ],
        "forbidden_actions": [
            "create_worktree",
            "copy_workspace",
            "apply_patch_to_candidate",
            "mutate_stable_runtime",
            "run_verification",
            "promote_candidate",
            "direct_merge",
            "remote_git_push",
            "self_apply_to_stable_runtime",
        ],
    }
    return validate_candidate_workspace_plan(plan)


def validate_candidate_workspace_plan(plan: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "runtime_level",
        "candidate_workspace_manager_enabled",
        "backend_authoritative",
        "target_repo",
        "candidate_root",
        "workspace_strategy",
        "fallback_strategy",
        "stable_checkpoint_required",
        "stable_checkpoint_id",
        "recovery_manifest_required",
        "safety_profile_required",
        "self_improvement_scope",
        "allowed_paths",
        "blocked_paths",
        "max_files",
        "max_risk_level",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in plan]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    allowed_paths = list(plan.get("allowed_paths", []))
    blocked_paths = list(plan.get("blocked_paths", []))
    invariants = {
        "schema_version": plan.get("schema_version") == SCHEMA_VERSION,
        "track_pr": plan.get("track_pr") == TRACK_PR,
        "next_required_pr": plan.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": plan.get("status") in {"ready", "blocked"},
        "blocked_reasons": plan.get("status") != "blocked" or bool(plan.get("blocking_reasons")),
        "runtime_level": plan.get("runtime_level") == CURRENT_RUNTIME_LEVEL,
        "candidate_workspace_manager_enabled": plan.get("candidate_workspace_manager_enabled") is (plan.get("status") == "ready"),
        "backend_authoritative": plan.get("backend_authoritative") is True,
        "workspace_strategy": plan.get("workspace_strategy") in STRATEGIES,
        "fallback_strategy": plan.get("fallback_strategy") in STRATEGIES,
        "stable_checkpoint_required": plan.get("stable_checkpoint_required") is True,
        "stable_checkpoint_id": bool(plan.get("stable_checkpoint_id")),
        "recovery_manifest_required": plan.get("recovery_manifest_required") is True,
        "safety_profile_required": plan.get("safety_profile_required") is True,
        "self_improvement_scope": plan.get("self_improvement_scope") in SELF_IMPROVEMENT_SCOPES,
        "allowed_paths": bool(allowed_paths) and not _validate_path_patterns("allowed_path", allowed_paths),
        "blocked_paths": not _validate_path_patterns("blocked_path", blocked_paths),
        "max_files": isinstance(plan.get("max_files"), int) and plan.get("max_files", 0) > 0,
        "max_risk_level": plan.get("max_risk_level") in RISK_LEVELS,
    }
    invariants.update({key: plan.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return plan


def write_candidate_workspace_plan(*, plan: dict[str, Any], destination: str | Path) -> Path:
    validated = validate_candidate_workspace_plan(plan)
    path = Path(destination).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_candidate_workspace_plan(*, manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    return validate_candidate_workspace_plan(json.loads(path.read_text(encoding="utf-8")))


def _validate_path_patterns(kind: str, paths: list[str]) -> list[str]:
    blocked: list[str] = []
    for raw in paths:
        normalized = _normalize_pattern(raw)
        if not normalized:
            blocked.append(f"{kind}_empty")
        if Path(normalized).is_absolute() or normalized.startswith("../") or "/../" in normalized:
            blocked.append(f"{kind}_must_be_repo_relative")
        if normalized in {".", "*", "**", "**/*"}:
            blocked.append(f"{kind}_too_broad")
    return blocked


def _normalize_pattern(path: str) -> str:
    return str(path).strip().replace("\\", "/").strip("/")


def _workspace_plan_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"candidate_workspace_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        resolved_parent = str(parent.resolve())
        return os.path.commonpath([resolved_parent, str(child.resolve())]) == resolved_parent
    except ValueError:
        return False
