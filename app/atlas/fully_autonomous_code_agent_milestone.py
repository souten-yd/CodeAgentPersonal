from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.self_improvement_autonomous_candidate_loop import (
    RUNTIME_LEVEL as CANDIDATE_LOOP_RUNTIME_LEVEL,
    SCHEMA_VERSION as CANDIDATE_LOOP_SCHEMA_VERSION,
    TRACK_PR as CANDIDATE_LOOP_TRACK,
    validate_self_improvement_autonomous_candidate_loop,
)

SCHEMA_VERSION = "atlas.fully_autonomous_code_agent_milestone.v1"
TRACK_PR = "PR-ATLAS-SCALE-160"
NEXT_REQUIRED_PR = "POST-SCALE-160-CONTINUOUS-IMPROVEMENT"
PREVIOUS_RUNTIME_LEVEL = CANDIDATE_LOOP_RUNTIME_LEVEL
RUNTIME_LEVEL = "level_8_fully_autonomous_code_agent"
REQUIRED_CONFIRMATION_TEXT = "AUTHORIZE FULLY AUTONOMOUS CODE AGENT MILESTONE"
_REQUIRED_FALSE_FLAGS = (
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
    "pointer_switch_execution_enabled",
    "pointer_switched",
    "recovery_execution_performed",
    "arbitrary_command_execution_enabled",
    "execute_all_enabled",
    "default_ui_promotion_enabled",
    "vue_authoritative",
    "vue_execution_controls_enabled",
)


def create_fully_autonomous_code_agent_milestone(
    *,
    autonomous_candidate_loop_path: str | Path,
    data_root: str | Path,
    milestone_evidence_refs: list[str] | None = None,
    rollback_evidence_refs: list[str] | None = None,
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
    loop_path = Path(autonomous_candidate_loop_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, loop_path, "autonomous_candidate_loop_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    loop = _read_candidate_loop(loop_path=loop_path, blocked=blocked)
    blocked.extend(_validate_candidate_loop_for_milestone(loop))
    evidence_refs = _safe_refs_or_block(milestone_evidence_refs or [], "milestone_evidence_refs", blocked)
    rollback_refs = _safe_refs_or_block(rollback_evidence_refs or [], "rollback_evidence_refs", blocked)
    if not evidence_refs:
        blocked.append("milestone_evidence_refs_required")
    if not rollback_refs:
        blocked.append("rollback_evidence_refs_required")
    if not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    ready = not blocked
    milestone = {
        "schema_version": SCHEMA_VERSION,
        "milestone_id": _milestone_id(created),
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
        "autonomous_candidate_loop_path": str(loop_path),
        "autonomous_candidate_loop_schema_version": str(loop.get("schema_version", "")),
        "autonomous_candidate_loop_track_pr": str(loop.get("track_pr", "")),
        "autonomous_candidate_loop_next_required_pr": str(loop.get("next_required_pr", "")),
        "autonomous_candidate_loop_ready": loop.get("self_improvement_autonomous_candidate_loop_enabled") is True,
        "milestone_evidence_refs": evidence_refs if ready else [],
        "rollback_evidence_refs": rollback_refs if ready else [],
        "fully_autonomous_code_agent_milestone_enabled": ready,
        "fully_autonomous_code_agent_ready": ready,
        "continuous_improvement_loop_ready": ready,
        "candidate_workspace_only_until_promotion_gate": True,
        "separate_default_ui_promotion_required": True,
        "separate_stable_runtime_mutation_gate_required": True,
        "separate_direct_merge_gate_required": True,
        "human_review_required_for_stable_mutation": True,
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
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "recovery_execution_performed": False,
        "arbitrary_command_execution_enabled": False,
        "execute_all_enabled": False,
        "default_ui_promotion_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
    }
    return validate_fully_autonomous_code_agent_milestone(milestone)


def validate_fully_autonomous_code_agent_milestone(milestone: dict[str, Any]) -> dict[str, Any]:
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
        "autonomous_candidate_loop_schema_version",
        "autonomous_candidate_loop_track_pr",
        "autonomous_candidate_loop_next_required_pr",
        "autonomous_candidate_loop_ready",
        "milestone_evidence_refs",
        "rollback_evidence_refs",
        "fully_autonomous_code_agent_milestone_enabled",
        "fully_autonomous_code_agent_ready",
        "continuous_improvement_loop_ready",
        "candidate_workspace_only_until_promotion_gate",
        "separate_default_ui_promotion_required",
        "separate_stable_runtime_mutation_gate_required",
        "separate_direct_merge_gate_required",
        "human_review_required_for_stable_mutation",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in milestone]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    ready = milestone.get("status") == "ready"
    invariants = {
        "schema_version": milestone.get("schema_version") == SCHEMA_VERSION,
        "track_pr": milestone.get("track_pr") == TRACK_PR,
        "next_required_pr": milestone.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": milestone.get("status") in {"ready", "blocked"},
        "blocking_reasons": ready or bool(milestone.get("blocking_reasons")),
        "previous_runtime_level": milestone.get("previous_runtime_level") == PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": milestone.get("runtime_level") == (RUNTIME_LEVEL if ready else PREVIOUS_RUNTIME_LEVEL),
        "target_runtime_level": milestone.get("target_runtime_level") == RUNTIME_LEVEL,
        "runtime_transition_authorized": milestone.get("runtime_transition_authorized") is ready,
        "backend_authoritative": milestone.get("backend_authoritative") is True,
        "autonomous_candidate_loop_schema_version": (not ready) or milestone.get("autonomous_candidate_loop_schema_version") == CANDIDATE_LOOP_SCHEMA_VERSION,
        "autonomous_candidate_loop_track_pr": (not ready) or milestone.get("autonomous_candidate_loop_track_pr") == CANDIDATE_LOOP_TRACK,
        "autonomous_candidate_loop_next_required_pr": (not ready) or milestone.get("autonomous_candidate_loop_next_required_pr") == TRACK_PR,
        "autonomous_candidate_loop_ready": (not ready) or milestone.get("autonomous_candidate_loop_ready") is True,
        "milestone_evidence_refs": (not ready) or bool(milestone.get("milestone_evidence_refs")),
        "rollback_evidence_refs": (not ready) or bool(milestone.get("rollback_evidence_refs")),
        "fully_autonomous_code_agent_milestone_enabled": milestone.get("fully_autonomous_code_agent_milestone_enabled") is ready,
        "fully_autonomous_code_agent_ready": milestone.get("fully_autonomous_code_agent_ready") is ready,
        "continuous_improvement_loop_ready": milestone.get("continuous_improvement_loop_ready") is ready,
        "candidate_workspace_only_until_promotion_gate": milestone.get("candidate_workspace_only_until_promotion_gate") is True,
        "separate_default_ui_promotion_required": milestone.get("separate_default_ui_promotion_required") is True,
        "separate_stable_runtime_mutation_gate_required": milestone.get("separate_stable_runtime_mutation_gate_required") is True,
        "separate_direct_merge_gate_required": milestone.get("separate_direct_merge_gate_required") is True,
        "human_review_required_for_stable_mutation": milestone.get("human_review_required_for_stable_mutation") is True,
    }
    invariants.update({key: milestone.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return milestone


def write_fully_autonomous_code_agent_milestone(*, data_root: str | Path, milestone: dict[str, Any]) -> Path:
    validated = validate_fully_autonomous_code_agent_milestone(milestone)
    root = Path(data_root).expanduser().resolve()
    milestone_id = str(validated.get("milestone_id", _milestone_id(_utc_now())))
    path = root / "atlas" / "fully_autonomous_code_agent_milestones" / milestone_id / "manifest.json"
    _ensure_under(root, path, "fully_autonomous_milestone_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_fully_autonomous_code_agent_milestone(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "fully_autonomous_milestone_outside_data_root")
    return validate_fully_autonomous_code_agent_milestone(json.loads(path.read_text(encoding="utf-8")))


def _read_candidate_loop(*, loop_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_self_improvement_autonomous_candidate_loop(json.loads(loop_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"autonomous_candidate_loop_read_failed:{type(exc).__name__}")
        return {}


def _validate_candidate_loop_for_milestone(loop: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if loop.get("schema_version") != CANDIDATE_LOOP_SCHEMA_VERSION:
        blocked.append("autonomous_candidate_loop_schema_required")
    if loop.get("track_pr") != CANDIDATE_LOOP_TRACK:
        blocked.append("autonomous_candidate_loop_track_required")
    if loop.get("next_required_pr") != TRACK_PR:
        blocked.append("autonomous_candidate_loop_next_pr_required")
    if loop.get("status") != "ready":
        blocked.append("ready_autonomous_candidate_loop_required")
    if loop.get("self_improvement_autonomous_candidate_loop_enabled") is not True:
        blocked.append("autonomous_candidate_loop_ready_required")
    if loop.get("candidate_workspace_only") is not True:
        blocked.append("candidate_workspace_only_required")
    if loop.get("recovery_plan_required_before_promotion") is not True:
        blocked.append("recovery_plan_before_promotion_required")
    for key in _REQUIRED_FALSE_FLAGS:
        if loop.get(key) is not False and key in loop:
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


def _milestone_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"fully_autonomous_code_agent_milestone_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
