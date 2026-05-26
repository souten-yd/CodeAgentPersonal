from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.self_improvement_candidate_verification_gate import (
    SCHEMA_VERSION as CANDIDATE_VERIFICATION_SCHEMA_VERSION,
    TRACK_PR as CANDIDATE_VERIFICATION_TRACK,
    validate_self_improvement_candidate_verification_gate,
)

SCHEMA_VERSION = "atlas.self_improvement_candidate_promotion_gate.v1"
TRACK_PR = "PR-ATLAS-SCALE-155"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-156"
REQUIRED_CONFIRMATION_TEXT = "PREPARE CANDIDATE PROMOTION GATE"
_REQUIRED_FALSE_FLAGS = (
    "release_pointer_switch_performed",
    "stable_runtime_mutation_enabled",
    "stable_runtime_mutation_performed",
    "command_execution_enabled",
    "command_execution_performed",
    "verification_execution_enabled",
    "verification_execution_performed",
    "verification_performed",
    "verification_result_fabricated",
    "promotion_performed",
    "self_apply_enabled",
    "self_modification_enabled",
    "direct_merge_enabled",
    "remote_git_push_enabled",
    "vue_authoritative",
    "vue_execution_controls_enabled",
    "autonomous_execution_enabled",
    "autonomous_loop_execution_enabled",
    "auto_continue_enabled",
    "execute_all_enabled",
)


def create_self_improvement_candidate_promotion_gate(
    *,
    candidate_verification_gate_path: str | Path,
    data_root: str | Path,
    release_pointer_path: str | Path,
    rollback_pointer_path: str | Path,
    stable_checkpoint_ref: str,
    recovery_manifest_ref: str,
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
    verification_path = Path(candidate_verification_gate_path).expanduser().resolve()
    release_pointer = Path(release_pointer_path).expanduser().resolve()
    rollback_pointer = Path(rollback_pointer_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, verification_path, "candidate_verification_gate_outside_data_root")
        _ensure_under(root, release_pointer, "release_pointer_outside_data_root")
        _ensure_under(root, rollback_pointer, "rollback_pointer_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    verification_gate = _read_verification_gate(verification_path=verification_path, blocked=blocked)
    blocked.extend(_validate_verification_gate_for_promotion(verification_gate))
    candidate_root = Path(str(verification_gate.get("candidate_root", ""))).expanduser().resolve()
    target_repo = Path(str(verification_gate.get("target_repo", ""))).expanduser().resolve()

    stable_ref = _safe_ref_or_block(stable_checkpoint_ref, "stable_checkpoint_ref", blocked)
    recovery_ref = _safe_ref_or_block(recovery_manifest_ref, "recovery_manifest_ref", blocked)
    if release_pointer.name != "current_release.json":
        blocked.append("release_pointer_filename_required")
    if rollback_pointer.name != "rollback_release.json":
        blocked.append("rollback_pointer_filename_required")
    if release_pointer == rollback_pointer:
        blocked.append("release_and_rollback_pointer_must_differ")
    if not stable_ref:
        blocked.append("stable_checkpoint_ref_required")
    if not recovery_ref:
        blocked.append("recovery_manifest_ref_required")
    if not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    status = "blocked" if blocked else "ready"
    result = {
        "schema_version": SCHEMA_VERSION,
        "promotion_gate_id": _promotion_gate_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": status,
        "blocking_reasons": list(dict.fromkeys(blocked)),
        "backend_authoritative": True,
        "reviewer": reviewer,
        "candidate_verification_gate_path": str(verification_path),
        "candidate_verification_schema_version": str(verification_gate.get("schema_version", "")),
        "candidate_verification_track_pr": str(verification_gate.get("track_pr", "")),
        "candidate_verification_next_required_pr": str(verification_gate.get("next_required_pr", "")),
        "candidate_root": str(candidate_root),
        "target_repo": str(target_repo),
        "changed_files": list(verification_gate.get("changed_files", [])) if status == "ready" else [],
        "verification_evidence_refs": list(verification_gate.get("verification_evidence_refs", [])) if status == "ready" else [],
        "stable_checkpoint_ref": stable_ref,
        "recovery_manifest_ref": recovery_ref,
        "release_pointer_path": str(release_pointer),
        "rollback_pointer_path": str(rollback_pointer),
        "candidate_promotion_gate_enabled": status == "ready",
        "candidate_promotion_ready": status == "ready",
        "release_pointer_switch_ready": status == "ready",
        "rollback_ready_pointer_required": True,
        "manual_only": True,
        "approval_required": True,
        "confirmation_text_required": REQUIRED_CONFIRMATION_TEXT,
        "release_pointer_switch_performed": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "verification_execution_enabled": False,
        "verification_execution_performed": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "promotion_performed": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
    }
    return validate_self_improvement_candidate_promotion_gate(result)


def validate_self_improvement_candidate_promotion_gate(result: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "blocking_reasons",
        "backend_authoritative",
        "candidate_verification_schema_version",
        "candidate_verification_track_pr",
        "candidate_verification_next_required_pr",
        "candidate_root",
        "target_repo",
        "changed_files",
        "verification_evidence_refs",
        "stable_checkpoint_ref",
        "recovery_manifest_ref",
        "release_pointer_path",
        "rollback_pointer_path",
        "candidate_promotion_gate_enabled",
        "candidate_promotion_ready",
        "release_pointer_switch_ready",
        "rollback_ready_pointer_required",
        "manual_only",
        "approval_required",
        "confirmation_text_required",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in result]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    is_ready = result.get("status") == "ready"
    candidate_root = Path(str(result.get("candidate_root", ""))).expanduser().resolve()
    target_repo = Path(str(result.get("target_repo", ""))).expanduser().resolve()
    release_pointer = Path(str(result.get("release_pointer_path", ""))).expanduser().resolve()
    rollback_pointer = Path(str(result.get("rollback_pointer_path", ""))).expanduser().resolve()
    invariants = {
        "schema_version": result.get("schema_version") == SCHEMA_VERSION,
        "track_pr": result.get("track_pr") == TRACK_PR,
        "next_required_pr": result.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": result.get("status") in {"blocked", "ready"},
        "blocking_reasons": is_ready or bool(result.get("blocking_reasons")),
        "backend_authoritative": result.get("backend_authoritative") is True,
        "candidate_verification_schema_version": result.get("candidate_verification_schema_version") == CANDIDATE_VERIFICATION_SCHEMA_VERSION,
        "candidate_verification_track_pr": result.get("candidate_verification_track_pr") == CANDIDATE_VERIFICATION_TRACK,
        "candidate_verification_next_required_pr": result.get("candidate_verification_next_required_pr") == TRACK_PR,
        "candidate_root_not_target_repo": (not is_ready) or (candidate_root != target_repo and not _is_relative_to(candidate_root, target_repo)),
        "changed_files": (not is_ready) or bool(result.get("changed_files")),
        "verification_evidence_refs": (not is_ready) or bool(result.get("verification_evidence_refs")),
        "stable_checkpoint_ref": (not is_ready) or bool(result.get("stable_checkpoint_ref")),
        "recovery_manifest_ref": (not is_ready) or bool(result.get("recovery_manifest_ref")),
        "release_pointer_name": (not is_ready) or release_pointer.name == "current_release.json",
        "rollback_pointer_name": (not is_ready) or rollback_pointer.name == "rollback_release.json",
        "release_and_rollback_pointer_differ": (not is_ready) or release_pointer != rollback_pointer,
        "candidate_promotion_gate_enabled": result.get("candidate_promotion_gate_enabled") is is_ready,
        "candidate_promotion_ready": result.get("candidate_promotion_ready") is is_ready,
        "release_pointer_switch_ready": result.get("release_pointer_switch_ready") is is_ready,
        "rollback_ready_pointer_required": result.get("rollback_ready_pointer_required") is True,
        "manual_only": result.get("manual_only") is True,
        "approval_required": result.get("approval_required") is True,
        "confirmation_text_required": result.get("confirmation_text_required") == REQUIRED_CONFIRMATION_TEXT,
    }
    invariants.update({key: result.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return result


def write_self_improvement_candidate_promotion_gate(*, data_root: str | Path, gate: dict[str, Any]) -> Path:
    validated = validate_self_improvement_candidate_promotion_gate(gate)
    root = Path(data_root).expanduser().resolve()
    gate_id = str(validated.get("promotion_gate_id", _promotion_gate_id(_utc_now())))
    path = root / "atlas" / "self_improvement_candidate_promotion_gates" / gate_id / "manifest.json"
    _ensure_under(root, path, "candidate_promotion_gate_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_self_improvement_candidate_promotion_gate(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "candidate_promotion_gate_outside_data_root")
    return validate_self_improvement_candidate_promotion_gate(json.loads(path.read_text(encoding="utf-8")))


def _read_verification_gate(*, verification_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_self_improvement_candidate_verification_gate(json.loads(verification_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"candidate_verification_gate_read_failed:{type(exc).__name__}")
        return {}


def _validate_verification_gate_for_promotion(gate: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if gate.get("schema_version") != CANDIDATE_VERIFICATION_SCHEMA_VERSION:
        blocked.append("candidate_verification_schema_required")
    if gate.get("track_pr") != CANDIDATE_VERIFICATION_TRACK:
        blocked.append("candidate_verification_track_required")
    if gate.get("next_required_pr") != TRACK_PR:
        blocked.append("candidate_verification_next_pr_required")
    if gate.get("status") != "ready":
        blocked.append("ready_candidate_verification_required")
    if gate.get("candidate_verification_ready") is not True:
        blocked.append("candidate_verification_ready_required")
    if not gate.get("verification_evidence_refs"):
        blocked.append("verification_evidence_refs_required")
    for key in (
        "command_execution_enabled",
        "command_execution_performed",
        "verification_execution_enabled",
        "verification_execution_performed",
        "verification_performed",
        "verification_result_fabricated",
        "candidate_promotion_enabled",
        "promotion_enabled",
        "promotion_performed",
        "stable_runtime_mutation_enabled",
        "stable_runtime_mutation_performed",
        "self_apply_enabled",
        "self_modification_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
    ):
        if gate.get(key) is not False and key in gate:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _safe_ref_or_block(value: str, field: str, blocked: list[str]) -> str:
    try:
        return _safe_ref(value)
    except ValueError as exc:
        blocked.append(f"{field}_{exc}")
        return ""


def _safe_ref(value: str) -> str:
    ref = str(value).strip().replace("\\", "/").strip("/")
    if not ref:
        raise ValueError("empty")
    path = Path(ref)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("must_be_relative")
    return path.as_posix()


def _promotion_gate_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"self_improvement_candidate_promotion_gate_{created_norm}_{uuid.uuid4().hex[:8]}"


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
