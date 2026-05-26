from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.autonomous_loop_execution_v1 import (
    RUNTIME_LEVEL as AUTONOMOUS_LOOP_RUNTIME_LEVEL,
    SCHEMA_VERSION as AUTONOMOUS_LOOP_SCHEMA_VERSION,
    TRACK_PR as AUTONOMOUS_LOOP_TRACK,
    validate_autonomous_loop_execution_v1,
)

SCHEMA_VERSION = "atlas.full_automation_mode_checkpoint.v1"
TRACK_PR = "PR-ATLAS-SCALE-158"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-159"
PREVIOUS_RUNTIME_LEVEL = AUTONOMOUS_LOOP_RUNTIME_LEVEL
RUNTIME_LEVEL = "level_6_full_automation_mode_checkpoint"
REQUIRED_CONFIRMATION_TEXT = "AUTHORIZE FULL AUTOMATION MODE CHECKPOINT"
_REQUIRED_FALSE_FLAGS = (
    "direct_merge_enabled",
    "direct_merge_performed",
    "remote_git_push_enabled",
    "remote_git_push_performed",
    "stable_runtime_mutation_enabled",
    "stable_runtime_mutation_performed",
    "self_apply_enabled",
    "self_apply_performed",
    "self_modification_enabled",
    "release_pointer_switch_performed",
    "recovery_execution_performed",
    "pointer_switch_execution_enabled",
    "pointer_switched",
    "default_ui_promotion_enabled",
    "vue_authoritative",
    "vue_execution_controls_enabled",
    "execute_all_enabled",
)


def create_full_automation_mode_checkpoint(
    *,
    autonomous_loop_execution_path: str | Path,
    data_root: str | Path,
    checkpoint_evidence_refs: list[str] | None = None,
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
    loop_path = Path(autonomous_loop_execution_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, loop_path, "autonomous_loop_execution_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    loop_session = _read_loop_session(loop_path=loop_path, blocked=blocked)
    blocked.extend(_validate_loop_session_for_checkpoint(loop_session))
    evidence_refs = _safe_refs_or_block(checkpoint_evidence_refs or [], "checkpoint_evidence_refs", blocked)
    if not evidence_refs:
        blocked.append("checkpoint_evidence_refs_required")
    if not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    authorized = not blocked
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": _checkpoint_id(created),
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
        "autonomous_loop_execution_path": str(loop_path),
        "autonomous_loop_schema_version": str(loop_session.get("schema_version", "")),
        "autonomous_loop_track_pr": str(loop_session.get("track_pr", "")),
        "autonomous_loop_next_required_pr": str(loop_session.get("next_required_pr", "")),
        "autonomous_loop_runtime_level": str(loop_session.get("runtime_level", "")),
        "autonomous_loop_execution_ready": loop_session.get("autonomous_loop_execution_v1_enabled") is True,
        "checkpoint_evidence_refs": evidence_refs if authorized else [],
        "full_automation_mode_checkpoint_enabled": authorized,
        "full_automation_mode_ready": authorized,
        "bounded_autonomous_execution_required": True,
        "recovery_plan_required": True,
        "human_review_required_for_stable_mutation": True,
        "arbitrary_command_execution_enabled": False,
        "command_execution_enabled": False,
        "direct_merge_enabled": False,
        "direct_merge_performed": False,
        "remote_git_push_enabled": False,
        "remote_git_push_performed": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "self_apply_enabled": False,
        "self_apply_performed": False,
        "self_modification_enabled": False,
        "release_pointer_switch_performed": False,
        "recovery_execution_performed": False,
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "default_ui_promotion_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "execute_all_enabled": False,
    }
    return validate_full_automation_mode_checkpoint(checkpoint)


def validate_full_automation_mode_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
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
        "autonomous_loop_schema_version",
        "autonomous_loop_track_pr",
        "autonomous_loop_next_required_pr",
        "autonomous_loop_runtime_level",
        "autonomous_loop_execution_ready",
        "checkpoint_evidence_refs",
        "full_automation_mode_checkpoint_enabled",
        "full_automation_mode_ready",
        "bounded_autonomous_execution_required",
        "recovery_plan_required",
        "human_review_required_for_stable_mutation",
        "arbitrary_command_execution_enabled",
        "command_execution_enabled",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in checkpoint]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    ready = checkpoint.get("status") == "ready"
    invariants = {
        "schema_version": checkpoint.get("schema_version") == SCHEMA_VERSION,
        "track_pr": checkpoint.get("track_pr") == TRACK_PR,
        "next_required_pr": checkpoint.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": checkpoint.get("status") in {"ready", "blocked"},
        "blocking_reasons": ready or bool(checkpoint.get("blocking_reasons")),
        "previous_runtime_level": checkpoint.get("previous_runtime_level") == PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": checkpoint.get("runtime_level") == (RUNTIME_LEVEL if ready else PREVIOUS_RUNTIME_LEVEL),
        "target_runtime_level": checkpoint.get("target_runtime_level") == RUNTIME_LEVEL,
        "runtime_transition_authorized": checkpoint.get("runtime_transition_authorized") is ready,
        "backend_authoritative": checkpoint.get("backend_authoritative") is True,
        "autonomous_loop_schema_version": (not ready) or checkpoint.get("autonomous_loop_schema_version") == AUTONOMOUS_LOOP_SCHEMA_VERSION,
        "autonomous_loop_track_pr": (not ready) or checkpoint.get("autonomous_loop_track_pr") == AUTONOMOUS_LOOP_TRACK,
        "autonomous_loop_next_required_pr": (not ready) or checkpoint.get("autonomous_loop_next_required_pr") == TRACK_PR,
        "autonomous_loop_runtime_level": (not ready) or checkpoint.get("autonomous_loop_runtime_level") == AUTONOMOUS_LOOP_RUNTIME_LEVEL,
        "autonomous_loop_execution_ready": (not ready) or checkpoint.get("autonomous_loop_execution_ready") is True,
        "checkpoint_evidence_refs": (not ready) or bool(checkpoint.get("checkpoint_evidence_refs")),
        "full_automation_mode_checkpoint_enabled": checkpoint.get("full_automation_mode_checkpoint_enabled") is ready,
        "full_automation_mode_ready": checkpoint.get("full_automation_mode_ready") is ready,
        "bounded_autonomous_execution_required": checkpoint.get("bounded_autonomous_execution_required") is True,
        "recovery_plan_required": checkpoint.get("recovery_plan_required") is True,
        "human_review_required_for_stable_mutation": checkpoint.get("human_review_required_for_stable_mutation") is True,
        "arbitrary_command_execution_enabled": checkpoint.get("arbitrary_command_execution_enabled") is False,
        "command_execution_enabled": checkpoint.get("command_execution_enabled") is False,
    }
    invariants.update({key: checkpoint.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return checkpoint


def write_full_automation_mode_checkpoint(*, data_root: str | Path, checkpoint: dict[str, Any]) -> Path:
    validated = validate_full_automation_mode_checkpoint(checkpoint)
    root = Path(data_root).expanduser().resolve()
    checkpoint_id = str(validated.get("checkpoint_id", _checkpoint_id(_utc_now())))
    path = root / "atlas" / "full_automation_mode_checkpoints" / checkpoint_id / "manifest.json"
    _ensure_under(root, path, "full_automation_mode_checkpoint_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_full_automation_mode_checkpoint(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "full_automation_mode_checkpoint_outside_data_root")
    return validate_full_automation_mode_checkpoint(json.loads(path.read_text(encoding="utf-8")))


def _read_loop_session(*, loop_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_autonomous_loop_execution_v1(json.loads(loop_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"autonomous_loop_execution_read_failed:{type(exc).__name__}")
        return {}


def _validate_loop_session_for_checkpoint(session: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if session.get("schema_version") != AUTONOMOUS_LOOP_SCHEMA_VERSION:
        blocked.append("autonomous_loop_schema_required")
    if session.get("track_pr") != AUTONOMOUS_LOOP_TRACK:
        blocked.append("autonomous_loop_track_required")
    if session.get("next_required_pr") != TRACK_PR:
        blocked.append("autonomous_loop_next_pr_required")
    if session.get("status") != "ready":
        blocked.append("ready_autonomous_loop_required")
    if session.get("runtime_level") != AUTONOMOUS_LOOP_RUNTIME_LEVEL:
        blocked.append("autonomous_loop_runtime_level_required")
    if session.get("autonomous_loop_execution_v1_enabled") is not True:
        blocked.append("autonomous_loop_execution_v1_required")
    if session.get("bounded_loop_execution") is not True:
        blocked.append("bounded_loop_execution_required")
    if session.get("stop_on_failure") is not True:
        blocked.append("stop_on_failure_required")
    if session.get("recovery_plan_required_before_each_iteration") is not True:
        blocked.append("recovery_plan_each_iteration_required")
    for key in _REQUIRED_FALSE_FLAGS:
        if session.get(key) is not False and key in session:
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


def _checkpoint_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"full_automation_mode_checkpoint_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
