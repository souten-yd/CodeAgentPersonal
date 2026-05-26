from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.self_improvement_candidate_promotion_gate import (
    SCHEMA_VERSION as CANDIDATE_PROMOTION_SCHEMA_VERSION,
    TRACK_PR as CANDIDATE_PROMOTION_TRACK,
    validate_self_improvement_candidate_promotion_gate,
)
from recovery.recover import (
    SCHEMA_VERSION as RECOVERY_MANIFEST_SCHEMA_VERSION,
    TRACK_PR as RECOVERY_MANIFEST_TRACK,
    validate_recovery_manifest,
)

SCHEMA_VERSION = "atlas.self_improvement_automatic_failure_recovery.v1"
TRACK_PR = "PR-ATLAS-SCALE-156"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-157"
REQUIRED_CONFIRMATION_TEXT = "PREPARE AUTOMATIC FAILURE RECOVERY"
_ALLOWED_RECOVERY_STRATEGIES = {
    "rollback_release_pointer",
    "hold_current_release",
    "open_recovery_review",
}
_REQUIRED_FALSE_FLAGS = (
    "recovery_execution_enabled",
    "recovery_execution_performed",
    "restore_execution_enabled",
    "restore_performed",
    "pointer_switch_execution_enabled",
    "pointer_switched",
    "file_copy_execution_enabled",
    "file_copied",
    "command_execution_enabled",
    "command_execution_performed",
    "verification_execution_enabled",
    "verification_execution_performed",
    "verification_performed",
    "verification_result_fabricated",
    "promotion_performed",
    "release_pointer_switch_performed",
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
    "llm_recovery_enabled",
)


def create_automatic_failure_recovery_plan(
    *,
    candidate_promotion_gate_path: str | Path,
    recovery_manifest_path: str | Path,
    data_root: str | Path,
    recovery_strategy: str = "rollback_release_pointer",
    max_recovery_attempts: int = 1,
    recovery_evidence_refs: list[str] | None = None,
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
    promotion_path = Path(candidate_promotion_gate_path).expanduser().resolve()
    recovery_path = Path(recovery_manifest_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, promotion_path, "candidate_promotion_gate_outside_data_root")
        _ensure_under(root, recovery_path, "recovery_manifest_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    promotion_gate = _read_candidate_promotion_gate(promotion_path=promotion_path, blocked=blocked)
    recovery_manifest = _read_recovery_manifest(recovery_path=recovery_path, blocked=blocked)
    blocked.extend(_validate_candidate_promotion_gate_for_recovery(promotion_gate))
    blocked.extend(_validate_recovery_manifest_for_plan(recovery_manifest, recovery_strategy))

    evidence_refs = _safe_refs_or_block(recovery_evidence_refs or [], "recovery_evidence_refs", blocked)
    if not evidence_refs:
        blocked.append("recovery_evidence_refs_required")
    if recovery_strategy not in _ALLOWED_RECOVERY_STRATEGIES:
        blocked.append("recovery_strategy_not_allowed")
    if not isinstance(max_recovery_attempts, int) or max_recovery_attempts < 1 or max_recovery_attempts > 3:
        blocked.append("max_recovery_attempts_must_be_1_to_3")
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
        "automatic_failure_recovery_id": _automatic_failure_recovery_id(created),
        "created_at": created,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "status": status,
        "blocking_reasons": list(dict.fromkeys(blocked)),
        "backend_authoritative": True,
        "reviewer": reviewer,
        "candidate_promotion_gate_path": str(promotion_path),
        "candidate_promotion_schema_version": str(promotion_gate.get("schema_version", "")),
        "candidate_promotion_track_pr": str(promotion_gate.get("track_pr", "")),
        "candidate_promotion_next_required_pr": str(promotion_gate.get("next_required_pr", "")),
        "candidate_root": str(promotion_gate.get("candidate_root", "")),
        "target_repo": str(promotion_gate.get("target_repo", "")),
        "stable_checkpoint_ref": str(promotion_gate.get("stable_checkpoint_ref", "")),
        "release_pointer_path": str(promotion_gate.get("release_pointer_path", "")),
        "rollback_pointer_path": str(promotion_gate.get("rollback_pointer_path", "")),
        "recovery_manifest_path": str(recovery_path),
        "recovery_manifest_schema_version": str(recovery_manifest.get("schema_version", "")),
        "recovery_manifest_track_pr": str(recovery_manifest.get("track_pr", "")),
        "recovery_manifest_next_required_pr": str(recovery_manifest.get("next_required_pr", "")),
        "external_supervisor_required": True,
        "application_runtime_independent": True,
        "target_runtime_imports_forbidden": True,
        "web_runtime_imports_forbidden": True,
        "model_provider_imports_forbidden": True,
        "bounded_recovery": True,
        "recovery_strategy": recovery_strategy,
        "max_recovery_attempts": max_recovery_attempts,
        "recovery_evidence_refs": evidence_refs if status == "ready" else [],
        "automatic_failure_recovery_enabled": status == "ready",
        "automatic_failure_recovery_ready": status == "ready",
        "rollback_release_pointer_plan_ready": status == "ready" and recovery_strategy == "rollback_release_pointer",
        "manual_operation_required": True,
        "approval_required": True,
        "confirmation_text_required": REQUIRED_CONFIRMATION_TEXT,
        "recovery_execution_enabled": False,
        "recovery_execution_performed": False,
        "restore_execution_enabled": False,
        "restore_performed": False,
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "file_copy_execution_enabled": False,
        "file_copied": False,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "verification_execution_enabled": False,
        "verification_execution_performed": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "promotion_performed": False,
        "release_pointer_switch_performed": False,
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
        "llm_recovery_enabled": False,
    }
    return validate_automatic_failure_recovery_plan(result)


def validate_automatic_failure_recovery_plan(result: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "track_pr",
        "next_required_pr",
        "status",
        "blocking_reasons",
        "backend_authoritative",
        "candidate_promotion_schema_version",
        "candidate_promotion_track_pr",
        "candidate_promotion_next_required_pr",
        "stable_checkpoint_ref",
        "release_pointer_path",
        "rollback_pointer_path",
        "recovery_manifest_schema_version",
        "recovery_manifest_track_pr",
        "recovery_manifest_next_required_pr",
        "external_supervisor_required",
        "application_runtime_independent",
        "target_runtime_imports_forbidden",
        "web_runtime_imports_forbidden",
        "model_provider_imports_forbidden",
        "bounded_recovery",
        "recovery_strategy",
        "max_recovery_attempts",
        "recovery_evidence_refs",
        "automatic_failure_recovery_enabled",
        "automatic_failure_recovery_ready",
        "rollback_release_pointer_plan_ready",
        "manual_operation_required",
        "approval_required",
        "confirmation_text_required",
        *_REQUIRED_FALSE_FLAGS,
    ]
    missing = [field for field in required if field not in result]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    is_ready = result.get("status") == "ready"
    strategy = result.get("recovery_strategy")
    attempts = result.get("max_recovery_attempts")
    invariants = {
        "schema_version": result.get("schema_version") == SCHEMA_VERSION,
        "track_pr": result.get("track_pr") == TRACK_PR,
        "next_required_pr": result.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": result.get("status") in {"blocked", "ready"},
        "blocking_reasons": is_ready or bool(result.get("blocking_reasons")),
        "backend_authoritative": result.get("backend_authoritative") is True,
        "candidate_promotion_schema_version": (not is_ready) or result.get("candidate_promotion_schema_version") == CANDIDATE_PROMOTION_SCHEMA_VERSION,
        "candidate_promotion_track_pr": (not is_ready) or result.get("candidate_promotion_track_pr") == CANDIDATE_PROMOTION_TRACK,
        "candidate_promotion_next_required_pr": (not is_ready) or result.get("candidate_promotion_next_required_pr") == TRACK_PR,
        "stable_checkpoint_ref": (not is_ready) or bool(result.get("stable_checkpoint_ref")),
        "release_pointer_path": (not is_ready) or str(result.get("release_pointer_path", "")).endswith("current_release.json"),
        "rollback_pointer_path": (not is_ready) or str(result.get("rollback_pointer_path", "")).endswith("rollback_release.json"),
        "recovery_manifest_schema_version": (not is_ready) or result.get("recovery_manifest_schema_version") == RECOVERY_MANIFEST_SCHEMA_VERSION,
        "recovery_manifest_track_pr": (not is_ready) or result.get("recovery_manifest_track_pr") == RECOVERY_MANIFEST_TRACK,
        "recovery_manifest_next_required_pr": (not is_ready) or result.get("recovery_manifest_next_required_pr") == "PR-ATLAS-SCALE-149",
        "external_supervisor_required": result.get("external_supervisor_required") is True,
        "application_runtime_independent": result.get("application_runtime_independent") is True,
        "target_runtime_imports_forbidden": result.get("target_runtime_imports_forbidden") is True,
        "web_runtime_imports_forbidden": result.get("web_runtime_imports_forbidden") is True,
        "model_provider_imports_forbidden": result.get("model_provider_imports_forbidden") is True,
        "bounded_recovery": result.get("bounded_recovery") is True,
        "recovery_strategy": strategy in _ALLOWED_RECOVERY_STRATEGIES,
        "max_recovery_attempts": isinstance(attempts, int) and 1 <= attempts <= 3,
        "recovery_evidence_refs": (not is_ready) or bool(result.get("recovery_evidence_refs")),
        "automatic_failure_recovery_enabled": result.get("automatic_failure_recovery_enabled") is is_ready,
        "automatic_failure_recovery_ready": result.get("automatic_failure_recovery_ready") is is_ready,
        "rollback_release_pointer_plan_ready": result.get("rollback_release_pointer_plan_ready") is (is_ready and strategy == "rollback_release_pointer"),
        "manual_operation_required": result.get("manual_operation_required") is True,
        "approval_required": result.get("approval_required") is True,
        "confirmation_text_required": result.get("confirmation_text_required") == REQUIRED_CONFIRMATION_TEXT,
    }
    invariants.update({key: result.get(key) is False for key in _REQUIRED_FALSE_FLAGS})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return result


def write_automatic_failure_recovery_plan(*, data_root: str | Path, plan: dict[str, Any]) -> Path:
    validated = validate_automatic_failure_recovery_plan(plan)
    root = Path(data_root).expanduser().resolve()
    recovery_id = str(validated.get("automatic_failure_recovery_id", _automatic_failure_recovery_id(_utc_now())))
    path = root / "atlas" / "automatic_failure_recovery" / recovery_id / "manifest.json"
    _ensure_under(root, path, "automatic_failure_recovery_plan_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_automatic_failure_recovery_plan(
    *, manifest_path: str | Path, data_root: str | Path | None = None
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "automatic_failure_recovery_plan_outside_data_root")
    return validate_automatic_failure_recovery_plan(json.loads(path.read_text(encoding="utf-8")))


def _read_candidate_promotion_gate(*, promotion_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_self_improvement_candidate_promotion_gate(json.loads(promotion_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"candidate_promotion_gate_read_failed:{type(exc).__name__}")
        return {}


def _read_recovery_manifest(*, recovery_path: Path, blocked: list[str]) -> dict[str, Any]:
    try:
        return validate_recovery_manifest(json.loads(recovery_path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive metadata path
        blocked.append(f"recovery_manifest_read_failed:{type(exc).__name__}")
        return {}


def _validate_candidate_promotion_gate_for_recovery(gate: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if gate.get("schema_version") != CANDIDATE_PROMOTION_SCHEMA_VERSION:
        blocked.append("candidate_promotion_schema_required")
    if gate.get("track_pr") != CANDIDATE_PROMOTION_TRACK:
        blocked.append("candidate_promotion_track_required")
    if gate.get("next_required_pr") != TRACK_PR:
        blocked.append("candidate_promotion_next_pr_required")
    if gate.get("status") != "ready":
        blocked.append("ready_candidate_promotion_required")
    if gate.get("candidate_promotion_ready") is not True:
        blocked.append("candidate_promotion_ready_required")
    if gate.get("release_pointer_switch_ready") is not True:
        blocked.append("release_pointer_switch_ready_required")
    if gate.get("rollback_ready_pointer_required") is not True:
        blocked.append("rollback_ready_pointer_required")
    for key in _REQUIRED_FALSE_FLAGS:
        if gate.get(key) is not False and key in gate:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _validate_recovery_manifest_for_plan(manifest: dict[str, Any], recovery_strategy: str) -> list[str]:
    blocked: list[str] = []
    if manifest.get("schema_version") != RECOVERY_MANIFEST_SCHEMA_VERSION:
        blocked.append("recovery_manifest_schema_required")
    if manifest.get("track_pr") != RECOVERY_MANIFEST_TRACK:
        blocked.append("recovery_manifest_track_required")
    if manifest.get("status") != "ready":
        blocked.append("ready_recovery_manifest_required")
    if manifest.get("external_supervisor") is not True:
        blocked.append("external_recovery_supervisor_required")
    if manifest.get("application_runtime_independent") is not True:
        blocked.append("runtime_independent_recovery_required")
    if recovery_strategy == "rollback_release_pointer" and manifest.get("plan_release_pointer_switch_allowed") is not True:
        blocked.append("rollback_strategy_requires_pointer_switch_plan")
    for key in (
        "imports_target_runtime",
        "imports_web_runtime",
        "imports_model_provider",
        "command_execution_enabled",
        "restore_execution_enabled",
        "pointer_switch_execution_enabled",
        "file_copy_execution_enabled",
        "network_access_required",
        "execution_performed",
        "restore_performed",
        "pointer_switched",
        "file_copied",
        "mutation_performed",
    ):
        if manifest.get(key) is not False and key in manifest:
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


def _automatic_failure_recovery_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"automatic_failure_recovery_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
