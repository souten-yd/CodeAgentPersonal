from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.self_improvement_candidate_apply import (
    SCHEMA_VERSION as CANDIDATE_APPLY_SCHEMA_VERSION,
    TRACK_PR as CANDIDATE_APPLY_TRACK,
    validate_self_improvement_candidate_apply,
)
from app.atlas.verification_allowlist import classify_verification_command

SCHEMA_VERSION = "atlas.self_improvement_candidate_verification_gate.v1"
TRACK_PR = "PR-ATLAS-SCALE-154"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-155"
_MAX_COMMANDS = 5
_REQUIRED_FALSE_FLAGS = (
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
)


def create_self_improvement_candidate_verification_gate(
    *,
    candidate_apply_result_path: str | Path,
    proposed_commands: list[str],
    verification_evidence_refs: list[str],
    data_root: str | Path,
    reviewer: str = "atlas",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    root = Path(data_root).expanduser().resolve()
    apply_path = Path(candidate_apply_result_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, apply_path, "candidate_apply_result_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    candidate_apply = _read_candidate_apply_result(apply_path=apply_path, blocked=blocked)
    blocked.extend(_validate_candidate_apply_for_verification(candidate_apply))
    candidate_root = Path(str(candidate_apply.get("candidate_root", ""))).expanduser().resolve()
    commands = [command.strip() for command in proposed_commands if command.strip()]
    if not commands:
        blocked.append("verification_commands_required")
    if len(commands) > _MAX_COMMANDS:
        blocked.append("too_many_verification_commands")

    command_results = [
        classify_verification_command(command=command, project_path=candidate_root, risk_level="strict_gate")
        for command in commands[:_MAX_COMMANDS]
    ]
    if any(not result.get("allowed") for result in command_results):
        blocked.append("only_allowlisted_candidate_verification_commands_allowed")

    evidence_refs: list[str] = []
    for ref in verification_evidence_refs:
        try:
            evidence_refs.append(_safe_ref(ref))
        except ValueError as exc:
            blocked.append(str(exc))
    if not evidence_refs:
        blocked.append("verification_evidence_refs_required")

    status = "blocked" if blocked else "ready"
    result = {
        "schema_version": SCHEMA_VERSION,
        "gate_id": _gate_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": status,
        "blocking_reasons": list(dict.fromkeys(blocked)),
        "backend_authoritative": True,
        "reviewer": reviewer,
        "candidate_apply_result_path": str(apply_path),
        "candidate_apply_schema_version": str(candidate_apply.get("schema_version", "")),
        "candidate_apply_track_pr": str(candidate_apply.get("track_pr", "")),
        "candidate_apply_next_required_pr": str(candidate_apply.get("next_required_pr", "")),
        "candidate_apply_id": str(candidate_apply.get("inner_apply_id", "")),
        "candidate_root": str(candidate_root),
        "target_repo": str(Path(str(candidate_apply.get("target_repo", ""))).expanduser().resolve()),
        "changed_files": list(candidate_apply.get("changed_files", [])) if status == "ready" else [],
        "proposed_commands": commands,
        "command_results": command_results,
        "allowed_commands": [result["command"] for result in command_results if result.get("allowed")],
        "blocked_commands": [result["command"] for result in command_results if not result.get("allowed")],
        "verification_evidence_refs": evidence_refs,
        "candidate_verification_gate_enabled": status == "ready",
        "candidate_verification_ready": status == "ready",
        "allowlisted_verification_only": True,
        "no_promote_without_evidence": True,
        "manual_only": True,
        "approval_required": True,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "verification_execution_enabled": False,
        "verification_execution_performed": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "candidate_promotion_enabled": False,
        "promotion_enabled": False,
        "promotion_performed": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
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
    return validate_self_improvement_candidate_verification_gate(result)


def validate_self_improvement_candidate_verification_gate(result: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "blocking_reasons",
        "backend_authoritative",
        "candidate_apply_schema_version",
        "candidate_apply_track_pr",
        "candidate_apply_next_required_pr",
        "candidate_root",
        "target_repo",
        "changed_files",
        "proposed_commands",
        "command_results",
        "allowed_commands",
        "blocked_commands",
        "verification_evidence_refs",
        "candidate_verification_gate_enabled",
        "candidate_verification_ready",
        "allowlisted_verification_only",
        "no_promote_without_evidence",
        "manual_only",
        "approval_required",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in result]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    is_ready = result.get("status") == "ready"
    candidate_root = Path(str(result.get("candidate_root", ""))).expanduser().resolve()
    target_repo = Path(str(result.get("target_repo", ""))).expanduser().resolve()
    command_results = list(result.get("command_results", []))
    invariants = {
        "schema_version": result.get("schema_version") == SCHEMA_VERSION,
        "track_pr": result.get("track_pr") == TRACK_PR,
        "next_required_pr": result.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": result.get("status") in {"blocked", "ready"},
        "blocking_reasons": is_ready or bool(result.get("blocking_reasons")),
        "backend_authoritative": result.get("backend_authoritative") is True,
        "candidate_apply_schema_version": result.get("candidate_apply_schema_version") == CANDIDATE_APPLY_SCHEMA_VERSION,
        "candidate_apply_track_pr": result.get("candidate_apply_track_pr") == CANDIDATE_APPLY_TRACK,
        "candidate_apply_next_required_pr": result.get("candidate_apply_next_required_pr") == TRACK_PR,
        "candidate_root_not_target_repo": (not is_ready) or (candidate_root != target_repo and not _is_relative_to(candidate_root, target_repo)),
        "changed_files": (not is_ready) or bool(result.get("changed_files")),
        "command_results": (not is_ready)
        or (0 < len(command_results) <= _MAX_COMMANDS and all(entry.get("allowed") for entry in command_results)),
        "allowed_commands": (not is_ready) or bool(result.get("allowed_commands")),
        "blocked_commands": (not is_ready) or not result.get("blocked_commands"),
        "verification_evidence_refs": (not is_ready) or bool(result.get("verification_evidence_refs")),
        "candidate_verification_gate_enabled": result.get("candidate_verification_gate_enabled") is is_ready,
        "candidate_verification_ready": result.get("candidate_verification_ready") is is_ready,
        "allowlisted_verification_only": result.get("allowlisted_verification_only") is True,
        "no_promote_without_evidence": result.get("no_promote_without_evidence") is True,
        "manual_only": result.get("manual_only") is True,
        "approval_required": result.get("approval_required") is True,
    }
    invariants.update({key: result.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return result


def write_self_improvement_candidate_verification_gate(*, data_root: str | Path, gate: dict[str, Any]) -> Path:
    validated = validate_self_improvement_candidate_verification_gate(gate)
    root = Path(data_root).expanduser().resolve()
    gate_id = str(validated.get("gate_id", _gate_id(_utc_now())))
    path = root / "atlas" / "self_improvement_candidate_verification_gates" / gate_id / "manifest.json"
    _ensure_under(root, path, "candidate_verification_gate_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_self_improvement_candidate_verification_gate(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "candidate_verification_gate_outside_data_root")
    return validate_self_improvement_candidate_verification_gate(json.loads(path.read_text(encoding="utf-8")))


def _read_candidate_apply_result(*, apply_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_self_improvement_candidate_apply(json.loads(apply_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"candidate_apply_result_read_failed:{type(exc).__name__}")
        return {}


def _validate_candidate_apply_for_verification(candidate_apply: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if candidate_apply.get("schema_version") != CANDIDATE_APPLY_SCHEMA_VERSION:
        blocked.append("candidate_apply_schema_required")
    if candidate_apply.get("track_pr") != CANDIDATE_APPLY_TRACK:
        blocked.append("candidate_apply_track_required")
    if candidate_apply.get("next_required_pr") != TRACK_PR:
        blocked.append("candidate_apply_next_pr_required")
    if candidate_apply.get("status") != "applied":
        blocked.append("applied_candidate_required")
    if candidate_apply.get("candidate_apply_performed") is not True:
        blocked.append("candidate_apply_performed_required")
    if candidate_apply.get("candidate_workspace_mutation_performed") is not True:
        blocked.append("candidate_workspace_mutation_required")
    for key in _REQUIRED_FALSE_FLAGS:
        if candidate_apply.get(key) is not False and key in candidate_apply:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _safe_ref(value: str) -> str:
    ref = str(value).strip().replace("\\", "/").strip("/")
    if not ref:
        raise ValueError("verification_evidence_ref_empty")
    path = Path(ref)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("verification_evidence_ref_must_be_relative")
    return path.as_posix()


def _gate_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"self_improvement_candidate_verification_gate_{created_norm}_{uuid.uuid4().hex[:8]}"


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
