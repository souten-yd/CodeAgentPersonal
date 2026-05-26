from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.bounded_loop_policy import SCHEMA_VERSION as LOOP_POLICY_SCHEMA_VERSION, read_bounded_loop_policy_v1
from app.atlas.bounded_retry_recovery import SCHEMA_VERSION as RETRY_RECOVERY_SCHEMA_VERSION, read_bounded_retry_recovery_metadata

SCHEMA_VERSION = "atlas.level2_runtime_transition_checkpoint.v1"
TRANSITION_PR = "PR-ATLAS-SCALE-138"
PREVIOUS_RUNTIME_LEVEL = "level_1_guarded_single_step"
RUNTIME_LEVEL = "level_2_guarded_bounded_loop"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-139"


def create_level2_runtime_transition_checkpoint(
    *,
    bounded_loop_policy_path: str | Path,
    retry_recovery_metadata_path: str | Path,
    data_root: str | Path | None = None,
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    stop_gate_ready: bool = False,
    verification_allowlist_ready: bool = False,
    artifact_capture_ready: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    loop_policy = read_bounded_loop_policy_v1(policy_path=bounded_loop_policy_path, data_root=data_root)["policy"]
    retry_metadata = read_bounded_retry_recovery_metadata(metadata_path=retry_recovery_metadata_path, data_root=data_root)["metadata"]
    root = Path(data_root if data_root is not None else Path(bounded_loop_policy_path).expanduser().resolve().parent).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, Path(bounded_loop_policy_path).expanduser().resolve(), "bounded_loop_policy_outside_data_root")
        _ensure_under(root, Path(retry_recovery_metadata_path).expanduser().resolve(), "retry_recovery_metadata_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_loop_policy(loop_policy))
    blocked.extend(_validate_retry_metadata(retry_metadata, loop_policy))
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if not stop_gate_ready:
        blocked.append("stop_gate_required")
    if not verification_allowlist_ready:
        blocked.append("verification_allowlist_required")
    if not artifact_capture_ready:
        blocked.append("artifact_capture_required")

    transition_authorized = not blocked
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": _checkpoint_id(created),
        "created_at": created,
        "transition_pr": TRANSITION_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "previous_runtime_level": PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": RUNTIME_LEVEL if transition_authorized else PREVIOUS_RUNTIME_LEVEL,
        "target_runtime_level": RUNTIME_LEVEL,
        "transition_authorized": transition_authorized,
        "transition_blocked": not transition_authorized,
        "blocking_reasons": sorted(set(blocked)),
        "bounded_loop_policy_path": str(Path(bounded_loop_policy_path).expanduser().resolve()),
        "retry_recovery_metadata_path": str(Path(retry_recovery_metadata_path).expanduser().resolve()),
        "data_root": str(root),
        "level2_guarded_bounded_loop_enabled": transition_authorized,
        "bounded_loop_execution_allowed": transition_authorized,
        "bounded_retry_candidate_allowed": transition_authorized,
        "max_iterations": int(loop_policy.get("max_iterations") or 0),
        "max_retries": int(retry_metadata.get("max_retries") if retry_metadata.get("max_retries") is not None else -1),
        "single_changed_file_only": True,
        "low_risk_only": True,
        "dry_run_required_each_iteration": True,
        "explicit_approval_required_each_iteration": True,
        "stop_gate_required": True,
        "verification_allowlist_required": True,
        "artifact_capture_required": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "retry_performed": False,
        "verification_performed": False,
        "rollback_performed": False,
        "restore_performed": False,
    }
    return validate_level2_runtime_transition_checkpoint(checkpoint)


def validate_level2_runtime_transition_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "transition_pr",
        "previous_runtime_level",
        "runtime_level",
        "target_runtime_level",
        "transition_authorized",
        "transition_blocked",
        "level2_guarded_bounded_loop_enabled",
        "bounded_loop_execution_allowed",
        "bounded_retry_candidate_allowed",
        "single_changed_file_only",
        "low_risk_only",
        "dry_run_required_each_iteration",
        "explicit_approval_required_each_iteration",
        "stop_gate_required",
        "verification_allowlist_required",
        "artifact_capture_required",
        "backend_authoritative",
        "vue_authoritative",
        "vue_execution_controls_enabled",
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
    ]
    missing = [field for field in required if field not in checkpoint]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    authorized = bool(checkpoint.get("transition_authorized"))
    invariants = {
        "schema_version": checkpoint.get("schema_version") == SCHEMA_VERSION,
        "transition_pr": checkpoint.get("transition_pr") == TRANSITION_PR,
        "previous_runtime_level": checkpoint.get("previous_runtime_level") == PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": checkpoint.get("runtime_level") == (RUNTIME_LEVEL if authorized else PREVIOUS_RUNTIME_LEVEL),
        "target_runtime_level": checkpoint.get("target_runtime_level") == RUNTIME_LEVEL,
        "transition_blocked": checkpoint.get("transition_blocked") is (not authorized),
        "level2_guarded_bounded_loop_enabled": checkpoint.get("level2_guarded_bounded_loop_enabled") is authorized,
        "bounded_loop_execution_allowed": checkpoint.get("bounded_loop_execution_allowed") is authorized,
        "bounded_retry_candidate_allowed": checkpoint.get("bounded_retry_candidate_allowed") is authorized,
        "single_changed_file_only": checkpoint.get("single_changed_file_only") is True,
        "low_risk_only": checkpoint.get("low_risk_only") is True,
        "dry_run_required_each_iteration": checkpoint.get("dry_run_required_each_iteration") is True,
        "explicit_approval_required_each_iteration": checkpoint.get("explicit_approval_required_each_iteration") is True,
        "stop_gate_required": checkpoint.get("stop_gate_required") is True,
        "verification_allowlist_required": checkpoint.get("verification_allowlist_required") is True,
        "artifact_capture_required": checkpoint.get("artifact_capture_required") is True,
        "backend_authoritative": checkpoint.get("backend_authoritative") is True,
        "vue_authoritative": checkpoint.get("vue_authoritative") is False,
        "vue_execution_controls_enabled": checkpoint.get("vue_execution_controls_enabled") is False,
        "autonomous_execution_enabled": checkpoint.get("autonomous_execution_enabled") is False,
        "auto_continue_enabled": checkpoint.get("auto_continue_enabled") is False,
        "execute_all_enabled": checkpoint.get("execute_all_enabled") is False,
        "self_modification_enabled": checkpoint.get("self_modification_enabled") is False,
        "direct_merge_enabled": checkpoint.get("direct_merge_enabled") is False,
        "remote_git_push_enabled": checkpoint.get("remote_git_push_enabled") is False,
        "execution_performed": checkpoint.get("execution_performed") is False,
        "mutation_performed": checkpoint.get("mutation_performed") is False,
        "retry_performed": checkpoint.get("retry_performed") is False,
        "verification_performed": checkpoint.get("verification_performed") is False,
        "rollback_performed": checkpoint.get("rollback_performed") is False,
        "restore_performed": checkpoint.get("restore_performed") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return checkpoint


def write_level2_runtime_transition_checkpoint(*, data_root: str | Path, checkpoint: dict[str, Any]) -> Path:
    validated = validate_level2_runtime_transition_checkpoint(checkpoint)
    root = Path(data_root).expanduser().resolve()
    checkpoint_id = str(validated["checkpoint_id"])
    path = root / "atlas" / "level2_runtime_transition_checkpoints" / checkpoint_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_level2_runtime_transition_checkpoint(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_level2_runtime_transition_checkpoint(json.loads(path.read_text(encoding="utf-8")))


def _validate_loop_policy(policy: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if policy.get("schema_version") != LOOP_POLICY_SCHEMA_VERSION:
        blocked.append("unsupported_bounded_loop_policy_schema")
    if policy.get("status") != "created" or policy.get("policy_only") is not True:
        blocked.append("bounded_loop_policy_required")
    for key in ("loop_execution_enabled", "bounded_retry_enabled", "autonomous_execution_enabled", "self_modification_enabled"):
        if policy.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    if policy.get("requires_human_approval_each_iteration") is not True:
        blocked.append("human_approval_each_iteration_required")
    if int(policy.get("max_iterations") or 0) < 1 or int(policy.get("max_iterations") or 0) > 3:
        blocked.append("max_iterations_invalid")
    if len(list(policy.get("changed_files", []))) != 1:
        blocked.append("single_changed_file_required")
    return blocked


def _validate_retry_metadata(metadata: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if metadata.get("schema_version") != RETRY_RECOVERY_SCHEMA_VERSION:
        blocked.append("unsupported_retry_recovery_schema")
    if metadata.get("status") != "created" or metadata.get("metadata_only") is not True:
        blocked.append("retry_recovery_metadata_required")
    if metadata.get("policy_id") != policy.get("policy_id"):
        blocked.append("retry_recovery_policy_id_mismatch")
    for key in ("retry_execution_enabled", "failure_recovery_execution_enabled", "auto_continue_enabled", "execute_all_enabled", "autonomous_execution_enabled"):
        if metadata.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    if metadata.get("requires_human_approval_before_retry") is not True:
        blocked.append("human_approval_before_retry_required")
    max_retries = int(metadata.get("max_retries") if metadata.get("max_retries") is not None else -1)
    if max_retries < 0 or max_retries > 2:
        blocked.append("max_retries_invalid")
    return blocked


def _checkpoint_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"level2_transition_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
