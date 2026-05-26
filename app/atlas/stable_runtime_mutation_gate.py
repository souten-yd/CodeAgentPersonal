from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.fully_autonomous_code_agent_milestone import (
    RUNTIME_LEVEL as FULLY_AUTONOMOUS_RUNTIME_LEVEL,
    SCHEMA_VERSION as FULLY_AUTONOMOUS_SCHEMA_VERSION,
    TRACK_PR as FULLY_AUTONOMOUS_TRACK,
    validate_fully_autonomous_code_agent_milestone,
)

SCHEMA_VERSION = "atlas.stable_runtime_mutation_gate.v1"
TRACK_PR = "POST-SCALE-160-STABLE-RUNTIME-MUTATION-GATE"
NEXT_REQUIRED_PR = "POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY"
REQUIRED_CONFIRMATION_TEXT = "PREPARE STABLE RUNTIME MUTATION GATE"

_REQUIRED_FALSE_FLAGS = (
    "stable_runtime_mutation_enabled",
    "stable_runtime_mutation_performed",
    "release_pointer_switch_performed",
    "pointer_switch_execution_enabled",
    "pointer_switched",
    "direct_merge_enabled",
    "direct_merge_performed",
    "remote_git_push_enabled",
    "remote_git_push_performed",
    "self_apply_enabled",
    "self_apply_performed",
    "self_modification_enabled",
    "recovery_execution_performed",
    "arbitrary_command_execution_enabled",
    "execute_all_enabled",
    "vue_authoritative",
    "vue_execution_controls_enabled",
)


def create_stable_runtime_mutation_gate(
    *,
    fully_autonomous_milestone_path: str | Path,
    data_root: str | Path,
    candidate_workspace_ref: str = "",
    stable_runtime_ref: str = "",
    rollback_evidence_refs: list[str] | None = None,
    verification_evidence_refs: list[str] | None = None,
    recovery_evidence_refs: list[str] | None = None,
    candidate_workspace_verified: bool = False,
    stable_runtime_snapshot_ready: bool = False,
    rollback_plan_ready: bool = False,
    recovery_plan_ready: bool = False,
    release_pointer_plan_ready: bool = False,
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
    milestone_path = Path(fully_autonomous_milestone_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, milestone_path, "fully_autonomous_milestone_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    milestone = _read_milestone(milestone_path=milestone_path, blocked=blocked)
    blocked.extend(_validate_milestone(milestone))
    candidate_ref = _safe_ref_or_block(candidate_workspace_ref, "candidate_workspace_ref", blocked)
    runtime_ref = _safe_ref_or_block(stable_runtime_ref, "stable_runtime_ref", blocked)
    rollback_refs = _safe_refs_or_block(rollback_evidence_refs or [], "rollback_evidence_refs", blocked)
    verification_refs = _safe_refs_or_block(verification_evidence_refs or [], "verification_evidence_refs", blocked)
    recovery_refs = _safe_refs_or_block(recovery_evidence_refs or [], "recovery_evidence_refs", blocked)

    if not candidate_ref:
        blocked.append("candidate_workspace_ref_required")
    if not runtime_ref:
        blocked.append("stable_runtime_ref_required")
    if not rollback_refs:
        blocked.append("rollback_evidence_refs_required")
    if not verification_refs:
        blocked.append("verification_evidence_refs_required")
    if not recovery_refs:
        blocked.append("recovery_evidence_refs_required")
    if not candidate_workspace_verified:
        blocked.append("candidate_workspace_verification_required")
    if not stable_runtime_snapshot_ready:
        blocked.append("stable_runtime_snapshot_required")
    if not rollback_plan_ready:
        blocked.append("rollback_plan_required")
    if not recovery_plan_ready:
        blocked.append("recovery_plan_required")
    if not release_pointer_plan_ready:
        blocked.append("release_pointer_plan_required")
    if not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    ready = not blocked
    gate = {
        "schema_version": SCHEMA_VERSION,
        "gate_id": _gate_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": "ready" if ready else "blocked",
        "blocking_reasons": list(dict.fromkeys(blocked)),
        "runtime_level": FULLY_AUTONOMOUS_RUNTIME_LEVEL,
        "backend_authoritative": True,
        "reviewer": reviewer,
        "fully_autonomous_milestone_path": str(milestone_path),
        "fully_autonomous_schema_version": str(milestone.get("schema_version", "")),
        "fully_autonomous_track_pr": str(milestone.get("track_pr", "")),
        "fully_autonomous_ready": milestone.get("fully_autonomous_code_agent_ready") is True,
        "candidate_workspace_ref": candidate_ref,
        "stable_runtime_ref": runtime_ref,
        "rollback_evidence_refs": rollback_refs if ready else [],
        "verification_evidence_refs": verification_refs if ready else [],
        "recovery_evidence_refs": recovery_refs if ready else [],
        "stable_runtime_mutation_gate_enabled": ready,
        "stable_runtime_mutation_ready": ready,
        "stable_runtime_mutation_apply_required": True,
        "candidate_workspace_verified": bool(candidate_workspace_verified),
        "stable_runtime_snapshot_ready": bool(stable_runtime_snapshot_ready),
        "rollback_plan_ready": bool(rollback_plan_ready),
        "recovery_plan_ready": bool(recovery_plan_ready),
        "release_pointer_plan_ready": bool(release_pointer_plan_ready),
        "backend_remains_authoritative": True,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "release_pointer_switch_performed": False,
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "direct_merge_enabled": False,
        "direct_merge_performed": False,
        "remote_git_push_enabled": False,
        "remote_git_push_performed": False,
        "self_apply_enabled": False,
        "self_apply_performed": False,
        "self_modification_enabled": False,
        "recovery_execution_performed": False,
        "arbitrary_command_execution_enabled": False,
        "execute_all_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
    }
    return validate_stable_runtime_mutation_gate(gate)


def validate_stable_runtime_mutation_gate(gate: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "blocking_reasons",
        "runtime_level",
        "backend_authoritative",
        "fully_autonomous_schema_version",
        "fully_autonomous_track_pr",
        "fully_autonomous_ready",
        "candidate_workspace_ref",
        "stable_runtime_ref",
        "rollback_evidence_refs",
        "verification_evidence_refs",
        "recovery_evidence_refs",
        "stable_runtime_mutation_gate_enabled",
        "stable_runtime_mutation_ready",
        "stable_runtime_mutation_apply_required",
        "candidate_workspace_verified",
        "stable_runtime_snapshot_ready",
        "rollback_plan_ready",
        "recovery_plan_ready",
        "release_pointer_plan_ready",
        "backend_remains_authoritative",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in gate]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    ready = gate.get("status") == "ready"
    invariants = {
        "schema_version": gate.get("schema_version") == SCHEMA_VERSION,
        "track_pr": gate.get("track_pr") == TRACK_PR,
        "next_required_pr": gate.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": gate.get("status") in {"ready", "blocked"},
        "blocking_reasons": ready or bool(gate.get("blocking_reasons")),
        "runtime_level": gate.get("runtime_level") == FULLY_AUTONOMOUS_RUNTIME_LEVEL,
        "backend_authoritative": gate.get("backend_authoritative") is True,
        "fully_autonomous_schema_version": (not ready) or gate.get("fully_autonomous_schema_version") == FULLY_AUTONOMOUS_SCHEMA_VERSION,
        "fully_autonomous_track_pr": (not ready) or gate.get("fully_autonomous_track_pr") == FULLY_AUTONOMOUS_TRACK,
        "fully_autonomous_ready": (not ready) or gate.get("fully_autonomous_ready") is True,
        "candidate_workspace_ref": (not ready) or bool(gate.get("candidate_workspace_ref")),
        "stable_runtime_ref": (not ready) or bool(gate.get("stable_runtime_ref")),
        "rollback_evidence_refs": (not ready) or bool(gate.get("rollback_evidence_refs")),
        "verification_evidence_refs": (not ready) or bool(gate.get("verification_evidence_refs")),
        "recovery_evidence_refs": (not ready) or bool(gate.get("recovery_evidence_refs")),
        "stable_runtime_mutation_gate_enabled": gate.get("stable_runtime_mutation_gate_enabled") is ready,
        "stable_runtime_mutation_ready": gate.get("stable_runtime_mutation_ready") is ready,
        "stable_runtime_mutation_apply_required": gate.get("stable_runtime_mutation_apply_required") is True,
        "candidate_workspace_verified": (not ready) or gate.get("candidate_workspace_verified") is True,
        "stable_runtime_snapshot_ready": (not ready) or gate.get("stable_runtime_snapshot_ready") is True,
        "rollback_plan_ready": (not ready) or gate.get("rollback_plan_ready") is True,
        "recovery_plan_ready": (not ready) or gate.get("recovery_plan_ready") is True,
        "release_pointer_plan_ready": (not ready) or gate.get("release_pointer_plan_ready") is True,
        "backend_remains_authoritative": gate.get("backend_remains_authoritative") is True,
    }
    invariants.update({key: gate.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return gate


def write_stable_runtime_mutation_gate(*, data_root: str | Path, gate: dict[str, Any]) -> Path:
    validated = validate_stable_runtime_mutation_gate(gate)
    root = Path(data_root).expanduser().resolve()
    gate_id = str(validated.get("gate_id", _gate_id(_utc_now())))
    path = root / "atlas" / "stable_runtime_mutation_gates" / gate_id / "manifest.json"
    _ensure_under(root, path, "stable_runtime_mutation_gate_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_stable_runtime_mutation_gate(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "stable_runtime_mutation_gate_outside_data_root")
    return validate_stable_runtime_mutation_gate(json.loads(path.read_text(encoding="utf-8")))


def _read_milestone(*, milestone_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_fully_autonomous_code_agent_milestone(json.loads(milestone_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"fully_autonomous_milestone_read_failed:{type(exc).__name__}")
        return {}


def _validate_milestone(milestone: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if milestone.get("schema_version") != FULLY_AUTONOMOUS_SCHEMA_VERSION:
        blocked.append("fully_autonomous_schema_required")
    if milestone.get("track_pr") != FULLY_AUTONOMOUS_TRACK:
        blocked.append("fully_autonomous_track_required")
    if milestone.get("status") != "ready":
        blocked.append("ready_fully_autonomous_milestone_required")
    if milestone.get("fully_autonomous_code_agent_ready") is not True:
        blocked.append("fully_autonomous_ready_required")
    for key in _REQUIRED_FALSE_FLAGS:
        if key in milestone and milestone.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _safe_ref_or_block(value: str, field: str, blocked: list[str]) -> str:
    try:
        return _safe_ref(value)
    except ValueError as exc:
        blocked.append(f"{field}_{exc}")
        return ""


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
    if len(path.parts) < 2:
        raise ValueError("must_include_directory")
    return path.as_posix()


def _gate_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"stable_runtime_mutation_gate_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
