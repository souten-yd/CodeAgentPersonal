from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.level2_runtime_transition_checkpoint import (
    RUNTIME_LEVEL as LEVEL2_RUNTIME_LEVEL,
    SCHEMA_VERSION as LEVEL2_CHECKPOINT_SCHEMA_VERSION,
    load_level2_runtime_transition_checkpoint,
)

SCHEMA_VERSION = "atlas.level3_autonomous_loop_candidate.v1"
TRANSITION_PR = "PR-ATLAS-SCALE-139"
PREVIOUS_RUNTIME_LEVEL = "level_2_guarded_bounded_loop"
CANDIDATE_RUNTIME_LEVEL = "level_3_autonomous_implementation_loop_candidate"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-140"
MAX_ALLOWED_ITERATIONS = 3
MAX_ALLOWED_RETRIES = 2
MAX_ALLOWED_RUNTIME_MINUTES = 60
_ALLOWED_RISK_LEVELS = {"low"}
_ALLOWED_VERIFICATION_COMMANDS = {"pytest", "npm_test", "npm_build", "atlas_smoke"}
_FORBIDDEN_COMMAND_CHARS = set(";&|`$<>")


def create_level3_autonomous_loop_candidate(
    *,
    level2_checkpoint_path: str | Path,
    data_root: str | Path | None = None,
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    max_iterations: int = 1,
    max_retries: int = 0,
    max_changed_files: int = 1,
    max_runtime_minutes: int = 20,
    max_risk_level: str = "low",
    verification_commands: list[str] | None = None,
    draft_pr_only: bool = True,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    checkpoint = load_level2_runtime_transition_checkpoint(manifest_path=level2_checkpoint_path, data_root=data_root)
    checkpoint_path = Path(level2_checkpoint_path).expanduser().resolve()
    root = Path(data_root if data_root is not None else checkpoint_path.parent).expanduser().resolve()
    commands = list(dict.fromkeys(verification_commands or ["pytest", "atlas_smoke"]))
    blocked: list[str] = []
    try:
        _ensure_under(root, checkpoint_path, "level2_checkpoint_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_level2_checkpoint(checkpoint))
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if max_iterations < 1 or max_iterations > MAX_ALLOWED_ITERATIONS:
        blocked.append("max_iterations_out_of_bounds")
    if max_retries < 0 or max_retries > MAX_ALLOWED_RETRIES:
        blocked.append("max_retries_out_of_bounds")
    if max_changed_files != 1:
        blocked.append("single_changed_file_required")
    if max_runtime_minutes < 1 or max_runtime_minutes > MAX_ALLOWED_RUNTIME_MINUTES:
        blocked.append("max_runtime_minutes_out_of_bounds")
    if max_risk_level not in _ALLOWED_RISK_LEVELS:
        blocked.append("max_risk_level_not_allowed")
    if draft_pr_only is not True:
        blocked.append("draft_pr_only_required")
    blocked.extend(_validate_verification_commands(commands))

    candidate_authorized = not blocked
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": _candidate_id(created),
        "created_at": created,
        "transition_pr": TRANSITION_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "previous_runtime_level": PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": CANDIDATE_RUNTIME_LEVEL if candidate_authorized else PREVIOUS_RUNTIME_LEVEL,
        "target_runtime_level": CANDIDATE_RUNTIME_LEVEL,
        "candidate_authorized": candidate_authorized,
        "candidate_blocked": not candidate_authorized,
        "blocking_reasons": sorted(set(blocked)),
        "level2_checkpoint_path": str(checkpoint_path),
        "data_root": str(root),
        "level3_autonomous_loop_candidate_enabled": candidate_authorized,
        "autonomous_loop_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "backend_authoritative": True,
        "draft_pr_only": True,
        "human_approval_required_for_apply": True,
        "human_approval_required_for_retry": True,
        "dry_run_required_before_apply": True,
        "stop_gate_required": True,
        "artifact_capture_required": True,
        "verification_allowlist_required": True,
        "max_iterations": max_iterations,
        "max_retries": max_retries,
        "max_changed_files": max_changed_files,
        "max_runtime_minutes": max_runtime_minutes,
        "max_risk_level": max_risk_level,
        "verification_commands": commands,
        "allowed_candidate_actions": [
            "plan_from_requirement",
            "prepare_patch_proposal",
            "prepare_dry_run_request",
            "evaluate_artifacts",
            "prepare_draft_pr_update_metadata",
            "request_human_approval",
        ],
        "forbidden_candidate_actions": [
            "execute_command",
            "apply_patch",
            "run_verification",
            "retry_without_human_approval",
            "auto_continue",
            "execute_all",
            "direct_merge",
            "remote_git_push",
            "self_modify",
            "vue_authoritative_execution",
        ],
        "execution_performed": False,
        "mutation_performed": False,
        "verification_performed": False,
        "retry_performed": False,
        "rollback_performed": False,
        "restore_performed": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    return validate_level3_autonomous_loop_candidate(candidate)


def validate_level3_autonomous_loop_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "transition_pr",
        "previous_runtime_level",
        "runtime_level",
        "target_runtime_level",
        "candidate_authorized",
        "candidate_blocked",
        "level3_autonomous_loop_candidate_enabled",
        "autonomous_loop_execution_enabled",
        "autonomous_execution_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "self_modification_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "backend_authoritative",
        "draft_pr_only",
        "human_approval_required_for_apply",
        "human_approval_required_for_retry",
        "dry_run_required_before_apply",
        "stop_gate_required",
        "artifact_capture_required",
        "verification_allowlist_required",
        "max_iterations",
        "max_retries",
        "max_changed_files",
        "max_runtime_minutes",
        "max_risk_level",
        "execution_performed",
        "mutation_performed",
        "verification_performed",
        "retry_performed",
        "rollback_performed",
        "restore_performed",
        "draft_pr_created",
        "draft_pr_updated",
    ]
    missing = [field for field in required if field not in candidate]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    authorized = bool(candidate.get("candidate_authorized"))
    invariants = {
        "schema_version": candidate.get("schema_version") == SCHEMA_VERSION,
        "transition_pr": candidate.get("transition_pr") == TRANSITION_PR,
        "previous_runtime_level": candidate.get("previous_runtime_level") == PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": candidate.get("runtime_level") == (CANDIDATE_RUNTIME_LEVEL if authorized else PREVIOUS_RUNTIME_LEVEL),
        "target_runtime_level": candidate.get("target_runtime_level") == CANDIDATE_RUNTIME_LEVEL,
        "candidate_blocked": candidate.get("candidate_blocked") is (not authorized),
        "level3_autonomous_loop_candidate_enabled": candidate.get("level3_autonomous_loop_candidate_enabled") is authorized,
        "autonomous_loop_execution_enabled": candidate.get("autonomous_loop_execution_enabled") is False,
        "autonomous_execution_enabled": candidate.get("autonomous_execution_enabled") is False,
        "automatic_patch_generation_enabled": candidate.get("automatic_patch_generation_enabled") is False,
        "automatic_patch_apply_enabled": candidate.get("automatic_patch_apply_enabled") is False,
        "automatic_verification_enabled": candidate.get("automatic_verification_enabled") is False,
        "auto_continue_enabled": candidate.get("auto_continue_enabled") is False,
        "execute_all_enabled": candidate.get("execute_all_enabled") is False,
        "self_modification_enabled": candidate.get("self_modification_enabled") is False,
        "direct_merge_enabled": candidate.get("direct_merge_enabled") is False,
        "remote_git_push_enabled": candidate.get("remote_git_push_enabled") is False,
        "vue_authoritative": candidate.get("vue_authoritative") is False,
        "vue_execution_controls_enabled": candidate.get("vue_execution_controls_enabled") is False,
        "backend_authoritative": candidate.get("backend_authoritative") is True,
        "draft_pr_only": candidate.get("draft_pr_only") is True,
        "human_approval_required_for_apply": candidate.get("human_approval_required_for_apply") is True,
        "human_approval_required_for_retry": candidate.get("human_approval_required_for_retry") is True,
        "dry_run_required_before_apply": candidate.get("dry_run_required_before_apply") is True,
        "stop_gate_required": candidate.get("stop_gate_required") is True,
        "artifact_capture_required": candidate.get("artifact_capture_required") is True,
        "verification_allowlist_required": candidate.get("verification_allowlist_required") is True,
        "max_iterations": int(candidate.get("max_iterations") or 0) >= 1 and int(candidate.get("max_iterations") or 0) <= MAX_ALLOWED_ITERATIONS,
        "max_retries": int(candidate.get("max_retries") if candidate.get("max_retries") is not None else -1) >= 0 and int(candidate.get("max_retries") if candidate.get("max_retries") is not None else -1) <= MAX_ALLOWED_RETRIES,
        "max_changed_files": candidate.get("max_changed_files") == 1,
        "max_runtime_minutes": int(candidate.get("max_runtime_minutes") or 0) >= 1 and int(candidate.get("max_runtime_minutes") or 0) <= MAX_ALLOWED_RUNTIME_MINUTES,
        "max_risk_level": candidate.get("max_risk_level") in _ALLOWED_RISK_LEVELS,
        "execution_performed": candidate.get("execution_performed") is False,
        "mutation_performed": candidate.get("mutation_performed") is False,
        "verification_performed": candidate.get("verification_performed") is False,
        "retry_performed": candidate.get("retry_performed") is False,
        "rollback_performed": candidate.get("rollback_performed") is False,
        "restore_performed": candidate.get("restore_performed") is False,
        "draft_pr_created": candidate.get("draft_pr_created") is False,
        "draft_pr_updated": candidate.get("draft_pr_updated") is False,
    }
    command_errors = _validate_verification_commands(list(candidate.get("verification_commands", [])))
    if command_errors:
        raise ValueError(f"invariant_violation:{','.join(sorted(set(command_errors)))}")
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return candidate


def write_level3_autonomous_loop_candidate(*, data_root: str | Path, candidate: dict[str, Any]) -> Path:
    validated = validate_level3_autonomous_loop_candidate(candidate)
    root = Path(data_root).expanduser().resolve()
    candidate_id = str(validated["candidate_id"])
    path = root / "atlas" / "level3_autonomous_loop_candidates" / candidate_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_level3_autonomous_loop_candidate(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_level3_autonomous_loop_candidate(json.loads(path.read_text(encoding="utf-8")))


def _validate_level2_checkpoint(checkpoint: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if checkpoint.get("schema_version") != LEVEL2_CHECKPOINT_SCHEMA_VERSION:
        blocked.append("unsupported_level2_checkpoint_schema")
    if checkpoint.get("transition_authorized") is not True:
        blocked.append("level2_transition_authorization_required")
    if checkpoint.get("runtime_level") != LEVEL2_RUNTIME_LEVEL:
        blocked.append("level2_runtime_level_required")
    if checkpoint.get("level2_guarded_bounded_loop_enabled") is not True:
        blocked.append("level2_guarded_bounded_loop_required")
    for key in (
        "autonomous_execution_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "self_modification_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "execution_performed",
        "mutation_performed",
        "retry_performed",
        "verification_performed",
        "rollback_performed",
        "restore_performed",
    ):
        if checkpoint.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _validate_verification_commands(commands: list[str]) -> list[str]:
    blocked: list[str] = []
    if not commands:
        blocked.append("verification_commands_required")
    for command in commands:
        if command not in _ALLOWED_VERIFICATION_COMMANDS:
            blocked.append("verification_command_not_allowed")
        if any(char in command for char in _FORBIDDEN_COMMAND_CHARS):
            blocked.append("verification_command_contains_forbidden_character")
    return blocked


def _candidate_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"level3_candidate_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
