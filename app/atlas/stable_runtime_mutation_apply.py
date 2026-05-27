from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.stable_runtime_mutation_gate import (
    NEXT_REQUIRED_PR as GATE_NEXT_REQUIRED_PR,
    SCHEMA_VERSION as GATE_SCHEMA_VERSION,
    TRACK_PR as GATE_TRACK_PR,
    load_stable_runtime_mutation_gate,
    validate_stable_runtime_mutation_gate,
)

SCHEMA_VERSION = "atlas.stable_runtime_mutation_apply.v1"
TRACK_PR = "POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY"
NEXT_REQUIRED_PR = "POST-SCALE-160-DIRECT-MERGE-GATE"
REQUIRED_CONFIRMATION_TEXT = "APPLY STABLE RUNTIME MUTATION"
_REQUIRED_FALSE_FLAGS = (
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


def create_stable_runtime_mutation_apply(
    *,
    gate: dict[str, Any],
    strict_gate_approved: bool = False,
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    reviewer: str = "atlas",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    blocked: list[str] = []
    valid_gate = _validate_ready_gate(gate, blocked)
    if not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    ready = not blocked
    apply_record = {
        "schema_version": SCHEMA_VERSION,
        "apply_id": _apply_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": "applied" if ready else "blocked",
        "blocking_reasons": list(dict.fromkeys(blocked)),
        "source_gate_schema_version": str(valid_gate.get("schema_version", "")),
        "source_gate_track_pr": str(valid_gate.get("track_pr", "")),
        "source_gate_next_required_pr": str(valid_gate.get("next_required_pr", "")),
        "source_gate_status": str(valid_gate.get("status", "")),
        "runtime_level": str(valid_gate.get("runtime_level", "")),
        "backend_authoritative": True,
        "reviewer": reviewer,
        "candidate_workspace_ref": str(valid_gate.get("candidate_workspace_ref", "")) if ready else "",
        "stable_runtime_ref": str(valid_gate.get("stable_runtime_ref", "")) if ready else "",
        "rollback_evidence_refs": list(valid_gate.get("rollback_evidence_refs", [])) if ready else [],
        "verification_evidence_refs": list(valid_gate.get("verification_evidence_refs", [])) if ready else [],
        "recovery_evidence_refs": list(valid_gate.get("recovery_evidence_refs", [])) if ready else [],
        "stable_runtime_mutation_apply_record_ready": ready,
        "stable_runtime_mutation_apply_record_written": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "stable_runtime_mutation_apply_required": False if ready else True,
        "stable_runtime_mutation_apply_record_only": True,
        "backend_remains_authoritative": True,
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
    return validate_stable_runtime_mutation_apply(apply_record)


def create_stable_runtime_mutation_apply_from_gate_file(
    *,
    gate_manifest_path: str | Path,
    data_root: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    gate = load_stable_runtime_mutation_gate(manifest_path=gate_manifest_path, data_root=data_root)
    return create_stable_runtime_mutation_apply(gate=gate, **kwargs)


def validate_stable_runtime_mutation_apply(apply_record: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "blocking_reasons",
        "source_gate_schema_version",
        "source_gate_track_pr",
        "source_gate_next_required_pr",
        "source_gate_status",
        "runtime_level",
        "backend_authoritative",
        "candidate_workspace_ref",
        "stable_runtime_ref",
        "rollback_evidence_refs",
        "verification_evidence_refs",
        "recovery_evidence_refs",
        "stable_runtime_mutation_enabled",
        "stable_runtime_mutation_performed",
        "stable_runtime_mutation_apply_record_ready",
        "stable_runtime_mutation_apply_record_written",
        "stable_runtime_mutation_apply_required",
        "stable_runtime_mutation_apply_record_only",
        "backend_remains_authoritative",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in apply_record]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    applied = apply_record.get("status") == "applied"
    invariants = {
        "schema_version": apply_record.get("schema_version") == SCHEMA_VERSION,
        "track_pr": apply_record.get("track_pr") == TRACK_PR,
        "next_required_pr": apply_record.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": apply_record.get("status") in {"applied", "blocked"},
        "blocking_reasons": applied or bool(apply_record.get("blocking_reasons")),
        "source_gate_schema_version": (not applied) or apply_record.get("source_gate_schema_version") == GATE_SCHEMA_VERSION,
        "source_gate_track_pr": (not applied) or apply_record.get("source_gate_track_pr") == GATE_TRACK_PR,
        "source_gate_next_required_pr": (not applied) or apply_record.get("source_gate_next_required_pr") == GATE_NEXT_REQUIRED_PR,
        "source_gate_status": (not applied) or apply_record.get("source_gate_status") == "ready",
        "runtime_level": bool(apply_record.get("runtime_level")) if applied else True,
        "backend_authoritative": apply_record.get("backend_authoritative") is True,
        "candidate_workspace_ref": (not applied) or bool(apply_record.get("candidate_workspace_ref")),
        "stable_runtime_ref": (not applied) or bool(apply_record.get("stable_runtime_ref")),
        "rollback_evidence_refs": (not applied) or bool(apply_record.get("rollback_evidence_refs")),
        "verification_evidence_refs": (not applied) or bool(apply_record.get("verification_evidence_refs")),
        "recovery_evidence_refs": (not applied) or bool(apply_record.get("recovery_evidence_refs")),
        "stable_runtime_mutation_enabled": apply_record.get("stable_runtime_mutation_enabled") is False,
        "stable_runtime_mutation_performed": apply_record.get("stable_runtime_mutation_performed") is False,
        "stable_runtime_mutation_apply_record_ready": apply_record.get("stable_runtime_mutation_apply_record_ready") is applied,
        "stable_runtime_mutation_apply_record_written": apply_record.get("stable_runtime_mutation_apply_record_written")
        in {False, applied},
        "stable_runtime_mutation_apply_required": apply_record.get("stable_runtime_mutation_apply_required") is (not applied),
        "stable_runtime_mutation_apply_record_only": apply_record.get("stable_runtime_mutation_apply_record_only") is True,
        "backend_remains_authoritative": apply_record.get("backend_remains_authoritative") is True,
    }
    invariants.update({key: apply_record.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return apply_record


def write_stable_runtime_mutation_apply(*, data_root: str | Path, apply_record: dict[str, Any]) -> Path:
    record_to_write = dict(apply_record)
    if record_to_write.get("status") == "applied":
        record_to_write["stable_runtime_mutation_apply_record_written"] = True
    validated = validate_stable_runtime_mutation_apply(record_to_write)
    root = Path(data_root).expanduser().resolve()
    apply_id = str(validated.get("apply_id", _apply_id(_utc_now())))
    path = root / "atlas" / "stable_runtime_mutation_applies" / apply_id / "manifest.json"
    _ensure_under(root, path, "stable_runtime_mutation_apply_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_stable_runtime_mutation_apply(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "stable_runtime_mutation_apply_outside_data_root")
    return validate_stable_runtime_mutation_apply(json.loads(path.read_text(encoding="utf-8")))


def _validate_ready_gate(gate: dict[str, Any], blocked: list[str]) -> dict[str, Any]:
    try:
        valid_gate = validate_stable_runtime_mutation_gate(gate)
    except Exception as exc:  # pragma: no cover - defensive metadata boundary
        blocked.append(f"stable_runtime_mutation_gate_invalid:{type(exc).__name__}")
        return {}
    if valid_gate.get("status") != "ready":
        blocked.append("ready_stable_runtime_mutation_gate_required")
    if valid_gate.get("track_pr") != GATE_TRACK_PR:
        blocked.append("stable_runtime_mutation_gate_track_required")
    if valid_gate.get("next_required_pr") != GATE_NEXT_REQUIRED_PR:
        blocked.append("stable_runtime_mutation_gate_next_pr_required")
    if valid_gate.get("stable_runtime_mutation_ready") is not True:
        blocked.append("stable_runtime_mutation_gate_ready_required")
    if valid_gate.get("stable_runtime_mutation_apply_required") is not True:
        blocked.append("stable_runtime_mutation_apply_required")
    return valid_gate


def _apply_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"stable_runtime_mutation_apply_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
