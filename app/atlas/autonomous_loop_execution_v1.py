from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.automation_safety_profile import (
    PROFILE_AUTONOMOUS_DEV_AGENT,
    SCHEMA_VERSION as SAFETY_PROFILE_SCHEMA_VERSION,
    TRACK_PR as SAFETY_PROFILE_TRACK,
    load_automation_safety_profile,
)
from app.atlas.self_improvement_automatic_failure_recovery import (
    SCHEMA_VERSION as RECOVERY_PLAN_SCHEMA_VERSION,
    TRACK_PR as RECOVERY_PLAN_TRACK,
    validate_automatic_failure_recovery_plan,
)

SCHEMA_VERSION = "atlas.autonomous_loop_execution_v1.v1"
TRACK_PR = "PR-ATLAS-SCALE-157"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-158"
PREVIOUS_RUNTIME_LEVEL = "level_4_self_improvement_platform"
RUNTIME_LEVEL = "level_5_autonomous_loop_execution_v1"
REQUIRED_CONFIRMATION_TEXT = "AUTHORIZE AUTONOMOUS LOOP EXECUTION V1"
_MAX_ITERATIONS = 3
_ALLOWED_LOOP_ACTIONS = {
    "read_backend_state",
    "select_next_candidate_step",
    "prepare_candidate_patch",
    "request_verification_gate",
    "request_recovery_plan",
    "stop_on_gate_failure",
    "record_progress_report",
}
_REQUIRED_FALSE_FLAGS = (
    "command_execution_enabled",
    "command_execution_performed",
    "arbitrary_command_execution_enabled",
    "patch_apply_to_stable_runtime_enabled",
    "stable_runtime_mutation_enabled",
    "stable_runtime_mutation_performed",
    "self_apply_enabled",
    "self_apply_performed",
    "self_modification_enabled",
    "direct_merge_enabled",
    "direct_merge_performed",
    "remote_git_push_enabled",
    "remote_git_push_performed",
    "release_pointer_switch_performed",
    "recovery_execution_performed",
    "pointer_switch_execution_enabled",
    "pointer_switched",
    "vue_authoritative",
    "vue_execution_controls_enabled",
    "default_ui_promotion_enabled",
    "llm_recovery_enabled",
    "execute_all_enabled",
)


def create_autonomous_loop_execution_v1(
    *,
    automation_safety_profile_path: str | Path,
    automatic_failure_recovery_plan_path: str | Path,
    data_root: str | Path,
    loop_goal: str,
    allowed_loop_actions: list[str] | None = None,
    max_iterations: int = 1,
    stop_on_failure: bool = True,
    require_recovery_plan_before_each_iteration: bool = True,
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
    profile_path = Path(automation_safety_profile_path).expanduser().resolve()
    recovery_path = Path(automatic_failure_recovery_plan_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, profile_path, "automation_safety_profile_outside_data_root")
        _ensure_under(root, recovery_path, "automatic_failure_recovery_plan_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    profile = _read_safety_profile(profile_path=profile_path, data_root=root, blocked=blocked)
    recovery_plan = _read_recovery_plan(recovery_path=recovery_path, blocked=blocked)
    blocked.extend(_validate_safety_profile_for_autonomous_loop(profile))
    blocked.extend(_validate_recovery_plan_for_autonomous_loop(recovery_plan))

    actions = list(dict.fromkeys(allowed_loop_actions or [
        "read_backend_state",
        "select_next_candidate_step",
        "request_verification_gate",
        "request_recovery_plan",
        "stop_on_gate_failure",
        "record_progress_report",
    ]))
    invalid_actions = [action for action in actions if action not in _ALLOWED_LOOP_ACTIONS]
    if invalid_actions:
        blocked.append("loop_action_not_allowed")
    if not actions:
        blocked.append("loop_actions_required")
    goal = str(loop_goal).strip()
    if not goal:
        blocked.append("loop_goal_required")
    if not isinstance(max_iterations, int) or max_iterations < 1 or max_iterations > _MAX_ITERATIONS:
        blocked.append("max_iterations_must_be_1_to_3")
    if stop_on_failure is not True:
        blocked.append("stop_on_failure_required")
    if require_recovery_plan_before_each_iteration is not True:
        blocked.append("recovery_plan_each_iteration_required")
    if not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    authorized = not blocked
    session = {
        "schema_version": SCHEMA_VERSION,
        "session_id": _session_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": "ready" if authorized else "blocked",
        "blocking_reasons": list(dict.fromkeys(blocked)),
        "previous_runtime_level": PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": RUNTIME_LEVEL if authorized else PREVIOUS_RUNTIME_LEVEL,
        "target_runtime_level": RUNTIME_LEVEL,
        "runtime_transition_authorized": authorized,
        "backend_authoritative": True,
        "reviewer": reviewer,
        "loop_goal": goal,
        "automation_safety_profile_path": str(profile_path),
        "automation_safety_profile_schema_version": str(profile.get("schema_version", "")),
        "automation_safety_profile_track_pr": str(profile.get("track_pr", "")),
        "automation_safety_profile": str(profile.get("automation_safety_profile", "")),
        "automatic_failure_recovery_plan_path": str(recovery_path),
        "automatic_failure_recovery_schema_version": str(recovery_plan.get("schema_version", "")),
        "automatic_failure_recovery_track_pr": str(recovery_plan.get("track_pr", "")),
        "automatic_failure_recovery_ready": recovery_plan.get("automatic_failure_recovery_ready") is True,
        "allowed_loop_actions": actions if authorized else [],
        "max_iterations": max_iterations,
        "bounded_loop_execution": True,
        "stop_on_failure": True,
        "recovery_plan_required_before_each_iteration": True,
        "human_review_required_for_stable_mutation": True,
        "autonomous_execution_enabled": authorized,
        "autonomous_loop_execution_enabled": authorized,
        "autonomous_loop_execution_v1_enabled": authorized,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "arbitrary_command_execution_enabled": False,
        "patch_apply_to_stable_runtime_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "self_apply_enabled": False,
        "self_apply_performed": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "direct_merge_performed": False,
        "remote_git_push_enabled": False,
        "remote_git_push_performed": False,
        "release_pointer_switch_performed": False,
        "recovery_execution_performed": False,
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "default_ui_promotion_enabled": False,
        "llm_recovery_enabled": False,
        "execute_all_enabled": False,
    }
    return validate_autonomous_loop_execution_v1(session)


def validate_autonomous_loop_execution_v1(session: dict[str, Any]) -> dict[str, Any]:
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
        "loop_goal",
        "automation_safety_profile_schema_version",
        "automation_safety_profile_track_pr",
        "automation_safety_profile",
        "automatic_failure_recovery_schema_version",
        "automatic_failure_recovery_track_pr",
        "automatic_failure_recovery_ready",
        "allowed_loop_actions",
        "max_iterations",
        "bounded_loop_execution",
        "stop_on_failure",
        "recovery_plan_required_before_each_iteration",
        "human_review_required_for_stable_mutation",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "autonomous_loop_execution_v1_enabled",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in session]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    ready = session.get("status") == "ready"
    actions = list(session.get("allowed_loop_actions", []))
    max_iterations = session.get("max_iterations")
    invariants = {
        "schema_version": session.get("schema_version") == SCHEMA_VERSION,
        "track_pr": session.get("track_pr") == TRACK_PR,
        "next_required_pr": session.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": session.get("status") in {"ready", "blocked"},
        "blocking_reasons": ready or bool(session.get("blocking_reasons")),
        "previous_runtime_level": session.get("previous_runtime_level") == PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": session.get("runtime_level") == (RUNTIME_LEVEL if ready else PREVIOUS_RUNTIME_LEVEL),
        "target_runtime_level": session.get("target_runtime_level") == RUNTIME_LEVEL,
        "runtime_transition_authorized": session.get("runtime_transition_authorized") is ready,
        "backend_authoritative": session.get("backend_authoritative") is True,
        "loop_goal": (not ready) or bool(str(session.get("loop_goal", "")).strip()),
        "automation_safety_profile_schema_version": (not ready) or session.get("automation_safety_profile_schema_version") == SAFETY_PROFILE_SCHEMA_VERSION,
        "automation_safety_profile_track_pr": (not ready) or session.get("automation_safety_profile_track_pr") == SAFETY_PROFILE_TRACK,
        "automation_safety_profile": (not ready) or session.get("automation_safety_profile") == PROFILE_AUTONOMOUS_DEV_AGENT,
        "automatic_failure_recovery_schema_version": (not ready) or session.get("automatic_failure_recovery_schema_version") == RECOVERY_PLAN_SCHEMA_VERSION,
        "automatic_failure_recovery_track_pr": (not ready) or session.get("automatic_failure_recovery_track_pr") == RECOVERY_PLAN_TRACK,
        "automatic_failure_recovery_ready": (not ready) or session.get("automatic_failure_recovery_ready") is True,
        "allowed_loop_actions": (not ready) or (bool(actions) and all(action in _ALLOWED_LOOP_ACTIONS for action in actions)),
        "max_iterations": isinstance(max_iterations, int) and 1 <= max_iterations <= _MAX_ITERATIONS,
        "bounded_loop_execution": session.get("bounded_loop_execution") is True,
        "stop_on_failure": session.get("stop_on_failure") is True,
        "recovery_plan_required_before_each_iteration": session.get("recovery_plan_required_before_each_iteration") is True,
        "human_review_required_for_stable_mutation": session.get("human_review_required_for_stable_mutation") is True,
        "autonomous_execution_enabled": session.get("autonomous_execution_enabled") is ready,
        "autonomous_loop_execution_enabled": session.get("autonomous_loop_execution_enabled") is ready,
        "autonomous_loop_execution_v1_enabled": session.get("autonomous_loop_execution_v1_enabled") is ready,
    }
    invariants.update({key: session.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return session


def write_autonomous_loop_execution_v1(*, data_root: str | Path, session: dict[str, Any]) -> Path:
    validated = validate_autonomous_loop_execution_v1(session)
    root = Path(data_root).expanduser().resolve()
    session_id = str(validated.get("session_id", _session_id(_utc_now())))
    path = root / "atlas" / "autonomous_loop_execution_v1" / session_id / "manifest.json"
    _ensure_under(root, path, "autonomous_loop_execution_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_autonomous_loop_execution_v1(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "autonomous_loop_execution_outside_data_root")
    return validate_autonomous_loop_execution_v1(json.loads(path.read_text(encoding="utf-8")))


def _read_safety_profile(*, profile_path: Path, data_root: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return load_automation_safety_profile(manifest_path=profile_path, data_root=data_root)
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"automation_safety_profile_read_failed:{type(exc).__name__}")
        return {}


def _read_recovery_plan(*, recovery_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_automatic_failure_recovery_plan(json.loads(recovery_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"automatic_failure_recovery_plan_read_failed:{type(exc).__name__}")
        return {}


def _validate_safety_profile_for_autonomous_loop(profile: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if profile.get("schema_version") != SAFETY_PROFILE_SCHEMA_VERSION:
        blocked.append("automation_safety_profile_schema_required")
    if profile.get("track_pr") != SAFETY_PROFILE_TRACK:
        blocked.append("automation_safety_profile_track_required")
    if profile.get("status") != "active":
        blocked.append("active_automation_safety_profile_required")
    if profile.get("automation_safety_profile") != PROFILE_AUTONOMOUS_DEV_AGENT:
        blocked.append("autonomous_dev_agent_profile_required")
    if profile.get("self_improvement_enabled") is not True:
        blocked.append("self_improvement_profile_required")
    capabilities = profile.get("capabilities") if isinstance(profile.get("capabilities"), dict) else {}
    if capabilities.get("allows_autonomous_loop_execution") is not True:
        blocked.append("autonomous_loop_capability_required")
    for key in (
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "stable_runtime_mutation_enabled",
        "self_apply_enabled",
        "self_modification_enabled",
        "execution_performed",
        "mutation_performed",
        "direct_merge_performed",
        "remote_git_push_performed",
        "stable_runtime_mutation_performed",
    ):
        if profile.get(key) is not False and key in profile:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _validate_recovery_plan_for_autonomous_loop(plan: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if plan.get("schema_version") != RECOVERY_PLAN_SCHEMA_VERSION:
        blocked.append("automatic_failure_recovery_schema_required")
    if plan.get("track_pr") != RECOVERY_PLAN_TRACK:
        blocked.append("automatic_failure_recovery_track_required")
    if plan.get("next_required_pr") != TRACK_PR:
        blocked.append("automatic_failure_recovery_next_pr_required")
    if plan.get("status") != "ready":
        blocked.append("ready_automatic_failure_recovery_required")
    if plan.get("automatic_failure_recovery_ready") is not True:
        blocked.append("automatic_failure_recovery_ready_required")
    if plan.get("bounded_recovery") is not True:
        blocked.append("bounded_recovery_required")
    for key in _REQUIRED_FALSE_FLAGS:
        if plan.get(key) is not False and key in plan:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _session_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"autonomous_loop_execution_v1_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
