from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.full_automation_mode_checkpoint import (
    RUNTIME_LEVEL as FULL_AUTOMATION_CHECKPOINT_LEVEL,
    SCHEMA_VERSION as FULL_AUTOMATION_CHECKPOINT_SCHEMA_VERSION,
    TRACK_PR as FULL_AUTOMATION_CHECKPOINT_TRACK,
    validate_full_automation_mode_checkpoint,
)

SCHEMA_VERSION = "atlas.self_improvement_autonomous_candidate_loop.v1"
TRACK_PR = "PR-ATLAS-SCALE-159"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-160"
PREVIOUS_RUNTIME_LEVEL = FULL_AUTOMATION_CHECKPOINT_LEVEL
RUNTIME_LEVEL = "level_7_self_improvement_autonomous_candidate_loop"
REQUIRED_CONFIRMATION_TEXT = "AUTHORIZE SELF IMPROVEMENT AUTONOMOUS CANDIDATE LOOP"
_MAX_ITERATIONS = 3
_ALLOWED_CANDIDATE_ACTIONS = {
    "read_candidate_state",
    "prepare_candidate_patch_preview",
    "request_candidate_verification_gate",
    "request_candidate_promotion_gate",
    "request_failure_recovery_plan",
    "record_candidate_loop_report",
    "stop_on_gate_failure",
}
_REQUIRED_FALSE_FLAGS = (
    "stable_runtime_mutation_enabled",
    "stable_runtime_mutation_performed",
    "patch_apply_to_stable_runtime_enabled",
    "self_apply_enabled",
    "self_apply_performed",
    "self_modification_enabled",
    "direct_merge_enabled",
    "direct_merge_performed",
    "remote_git_push_enabled",
    "remote_git_push_performed",
    "release_pointer_switch_performed",
    "pointer_switch_execution_enabled",
    "pointer_switched",
    "recovery_execution_performed",
    "arbitrary_command_execution_enabled",
    "execute_all_enabled",
    "default_ui_promotion_enabled",
    "vue_authoritative",
    "vue_execution_controls_enabled",
)


def create_self_improvement_autonomous_candidate_loop(
    *,
    full_automation_checkpoint_path: str | Path,
    data_root: str | Path,
    candidate_root: str | Path,
    target_repo: str | Path,
    loop_goal: str,
    allowed_candidate_actions: list[str] | None = None,
    max_iterations: int = 1,
    checkpoint_evidence_refs: list[str] | None = None,
    stop_on_gate_failure: bool = True,
    require_recovery_plan_before_promotion: bool = True,
    strict_gate_approved: bool = False,
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    reviewer: str = "atlas",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    root = Path(data_root).expanduser().resolve()
    checkpoint_path = Path(full_automation_checkpoint_path).expanduser().resolve()
    candidate = Path(candidate_root).expanduser().resolve()
    target = Path(target_repo).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, checkpoint_path, "full_automation_checkpoint_outside_data_root")
        _ensure_under(root, candidate, "candidate_root_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))
    if candidate == target or _is_relative_to(candidate, target):
        blocked.append("candidate_root_must_not_be_stable_target_repo")

    checkpoint = _read_checkpoint(checkpoint_path=checkpoint_path, blocked=blocked)
    blocked.extend(_validate_checkpoint_for_candidate_loop(checkpoint))
    actions = list(dict.fromkeys(allowed_candidate_actions or [
        "read_candidate_state",
        "prepare_candidate_patch_preview",
        "request_candidate_verification_gate",
        "request_failure_recovery_plan",
        "record_candidate_loop_report",
        "stop_on_gate_failure",
    ]))
    invalid_actions = [action for action in actions if action not in _ALLOWED_CANDIDATE_ACTIONS]
    if invalid_actions:
        blocked.append("candidate_loop_action_not_allowed")
    if not actions:
        blocked.append("candidate_loop_actions_required")
    if not str(loop_goal).strip():
        blocked.append("loop_goal_required")
    if not isinstance(max_iterations, int) or max_iterations < 1 or max_iterations > _MAX_ITERATIONS:
        blocked.append("max_iterations_must_be_1_to_3")
    evidence_refs = _safe_refs_or_block(checkpoint_evidence_refs or [], "checkpoint_evidence_refs", blocked)
    if not evidence_refs:
        blocked.append("checkpoint_evidence_refs_required")
    if stop_on_gate_failure is not True:
        blocked.append("stop_on_gate_failure_required")
    if require_recovery_plan_before_promotion is not True:
        blocked.append("recovery_plan_before_promotion_required")
    if not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    ready = not blocked
    result = {
        "schema_version": SCHEMA_VERSION,
        "candidate_loop_id": _candidate_loop_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": "ready" if ready else "blocked",
        "blocking_reasons": list(dict.fromkeys(blocked)),
        "previous_runtime_level": PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": RUNTIME_LEVEL if ready else PREVIOUS_RUNTIME_LEVEL,
        "target_runtime_level": RUNTIME_LEVEL,
        "runtime_transition_authorized": ready,
        "backend_authoritative": True,
        "reviewer": reviewer,
        "full_automation_checkpoint_path": str(checkpoint_path),
        "full_automation_checkpoint_schema_version": str(checkpoint.get("schema_version", "")),
        "full_automation_checkpoint_track_pr": str(checkpoint.get("track_pr", "")),
        "full_automation_checkpoint_next_required_pr": str(checkpoint.get("next_required_pr", "")),
        "full_automation_mode_ready": checkpoint.get("full_automation_mode_ready") is True,
        "candidate_root": str(candidate),
        "target_repo": str(target),
        "loop_goal": str(loop_goal).strip(),
        "allowed_candidate_actions": actions if ready else [],
        "max_iterations": max_iterations,
        "checkpoint_evidence_refs": evidence_refs if ready else [],
        "candidate_workspace_only": True,
        "autonomous_candidate_loop_enabled": ready,
        "self_improvement_autonomous_candidate_loop_enabled": ready,
        "stop_on_gate_failure": True,
        "recovery_plan_required_before_promotion": True,
        "human_review_required_for_stable_mutation": True,
        "candidate_patch_preview_enabled": ready,
        "candidate_verification_gate_request_enabled": ready,
        "candidate_promotion_gate_request_enabled": ready,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "patch_apply_to_stable_runtime_enabled": False,
        "self_apply_enabled": False,
        "self_apply_performed": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "direct_merge_performed": False,
        "remote_git_push_enabled": False,
        "remote_git_push_performed": False,
        "release_pointer_switch_performed": False,
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "recovery_execution_performed": False,
        "arbitrary_command_execution_enabled": False,
        "execute_all_enabled": False,
        "default_ui_promotion_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
    }
    return validate_self_improvement_autonomous_candidate_loop(result)


def validate_self_improvement_autonomous_candidate_loop(result: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "blocking_reasons",
        "previous_runtime_level",
        "runtime_level",
        "target_runtime_level",
        "runtime_transition_authorized",
        "backend_authoritative",
        "full_automation_checkpoint_schema_version",
        "full_automation_checkpoint_track_pr",
        "full_automation_checkpoint_next_required_pr",
        "full_automation_mode_ready",
        "candidate_root",
        "target_repo",
        "loop_goal",
        "allowed_candidate_actions",
        "max_iterations",
        "checkpoint_evidence_refs",
        "candidate_workspace_only",
        "autonomous_candidate_loop_enabled",
        "self_improvement_autonomous_candidate_loop_enabled",
        "stop_on_gate_failure",
        "recovery_plan_required_before_promotion",
        "human_review_required_for_stable_mutation",
        "candidate_patch_preview_enabled",
        "candidate_verification_gate_request_enabled",
        "candidate_promotion_gate_request_enabled",
        "command_execution_enabled",
        "command_execution_performed",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in result]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    ready = result.get("status") == "ready"
    candidate = Path(str(result.get("candidate_root", ""))).expanduser().resolve()
    target = Path(str(result.get("target_repo", ""))).expanduser().resolve()
    actions = list(result.get("allowed_candidate_actions", []))
    max_iterations = result.get("max_iterations")
    invariants = {
        "schema_version": result.get("schema_version") == SCHEMA_VERSION,
        "track_pr": result.get("track_pr") == TRACK_PR,
        "next_required_pr": result.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": result.get("status") in {"ready", "blocked"},
        "blocking_reasons": ready or bool(result.get("blocking_reasons")),
        "previous_runtime_level": result.get("previous_runtime_level") == PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": result.get("runtime_level") == (RUNTIME_LEVEL if ready else PREVIOUS_RUNTIME_LEVEL),
        "target_runtime_level": result.get("target_runtime_level") == RUNTIME_LEVEL,
        "runtime_transition_authorized": result.get("runtime_transition_authorized") is ready,
        "backend_authoritative": result.get("backend_authoritative") is True,
        "full_automation_checkpoint_schema_version": (not ready) or result.get("full_automation_checkpoint_schema_version") == FULL_AUTOMATION_CHECKPOINT_SCHEMA_VERSION,
        "full_automation_checkpoint_track_pr": (not ready) or result.get("full_automation_checkpoint_track_pr") == FULL_AUTOMATION_CHECKPOINT_TRACK,
        "full_automation_checkpoint_next_required_pr": (not ready) or result.get("full_automation_checkpoint_next_required_pr") == TRACK_PR,
        "full_automation_mode_ready": (not ready) or result.get("full_automation_mode_ready") is True,
        "candidate_root_not_target_repo": (not ready) or (candidate != target and not _is_relative_to(candidate, target)),
        "loop_goal": (not ready) or bool(str(result.get("loop_goal", "")).strip()),
        "allowed_candidate_actions": (not ready) or (bool(actions) and all(action in _ALLOWED_CANDIDATE_ACTIONS for action in actions)),
        "max_iterations": isinstance(max_iterations, int) and 1 <= max_iterations <= _MAX_ITERATIONS,
        "checkpoint_evidence_refs": (not ready) or bool(result.get("checkpoint_evidence_refs")),
        "candidate_workspace_only": result.get("candidate_workspace_only") is True,
        "autonomous_candidate_loop_enabled": result.get("autonomous_candidate_loop_enabled") is ready,
        "self_improvement_autonomous_candidate_loop_enabled": result.get("self_improvement_autonomous_candidate_loop_enabled") is ready,
        "stop_on_gate_failure": result.get("stop_on_gate_failure") is True,
        "recovery_plan_required_before_promotion": result.get("recovery_plan_required_before_promotion") is True,
        "human_review_required_for_stable_mutation": result.get("human_review_required_for_stable_mutation") is True,
        "candidate_patch_preview_enabled": result.get("candidate_patch_preview_enabled") is ready,
        "candidate_verification_gate_request_enabled": result.get("candidate_verification_gate_request_enabled") is ready,
        "candidate_promotion_gate_request_enabled": result.get("candidate_promotion_gate_request_enabled") is ready,
        "command_execution_enabled": result.get("command_execution_enabled") is False,
        "command_execution_performed": result.get("command_execution_performed") is False,
    }
    invariants.update({key: result.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return result


def write_self_improvement_autonomous_candidate_loop(*, data_root: str | Path, loop: dict[str, Any]) -> Path:
    validated = validate_self_improvement_autonomous_candidate_loop(loop)
    root = Path(data_root).expanduser().resolve()
    loop_id = str(validated.get("candidate_loop_id", _candidate_loop_id(_utc_now())))
    path = root / "atlas" / "self_improvement_autonomous_candidate_loops" / loop_id / "manifest.json"
    _ensure_under(root, path, "candidate_loop_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_self_improvement_autonomous_candidate_loop(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "candidate_loop_outside_data_root")
    return validate_self_improvement_autonomous_candidate_loop(json.loads(path.read_text(encoding="utf-8")))


def _read_checkpoint(*, checkpoint_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_full_automation_mode_checkpoint(json.loads(checkpoint_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"full_automation_checkpoint_read_failed:{type(exc).__name__}")
        return {}


def _validate_checkpoint_for_candidate_loop(checkpoint: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if checkpoint.get("schema_version") != FULL_AUTOMATION_CHECKPOINT_SCHEMA_VERSION:
        blocked.append("full_automation_checkpoint_schema_required")
    if checkpoint.get("track_pr") != FULL_AUTOMATION_CHECKPOINT_TRACK:
        blocked.append("full_automation_checkpoint_track_required")
    if checkpoint.get("next_required_pr") != TRACK_PR:
        blocked.append("full_automation_checkpoint_next_pr_required")
    if checkpoint.get("status") != "ready":
        blocked.append("ready_full_automation_checkpoint_required")
    if checkpoint.get("full_automation_mode_ready") is not True:
        blocked.append("full_automation_mode_ready_required")
    for key in _REQUIRED_FALSE_FLAGS:
        if checkpoint.get(key) is not False and key in checkpoint:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _safe_refs_or_block(values: list[str], field: str, blocked: list[str]) -> list[str]:
    refs: list[str] = []
    for value in values:
        try:
            refs.append(_safe_ref(value))
        except ValueError as exc:
            blocked.append(f"{field}_{exc}")
    return refs


def _safe_ref(value: str) -> str:
    ref = str(value).strip().replace("\\", "/").strip("/")
    if not ref:
        raise ValueError("empty")
    path = Path(ref)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("must_be_relative")
    return path.as_posix()


def _candidate_loop_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"self_improvement_autonomous_candidate_loop_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([str(parent.resolve()), str(child.resolve())]) == str(parent.resolve())
    except ValueError:
        return False
