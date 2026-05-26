from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.bounded_loop_policy import SCHEMA_VERSION as LOOP_POLICY_SCHEMA_VERSION, read_bounded_loop_policy_v1

SCHEMA_VERSION = "atlas.bounded_retry_recovery.v1"
MAX_ALLOWED_RETRIES = 2
_ALLOWED_FAILURE_CLASSES = {"verification_failed", "dry_run_failed", "policy_blocked", "transient_tool_failure"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _validate_policy(policy: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if policy.get("schema_version") != LOOP_POLICY_SCHEMA_VERSION:
        blocked.append("unsupported_bounded_loop_policy_schema")
    if policy.get("status") != "created" or policy.get("policy_only") is not True:
        blocked.append("bounded_loop_policy_required")
    if policy.get("loop_execution_enabled") is not False:
        blocked.append("loop_execution_enabled_must_be_false")
    if policy.get("bounded_retry_enabled") is not False:
        blocked.append("bounded_retry_must_not_be_pre_enabled")
    if policy.get("autonomous_execution_enabled") is not False:
        blocked.append("autonomous_execution_enabled_must_be_false")
    if policy.get("self_modification_enabled") is not False:
        blocked.append("self_modification_enabled_must_be_false")
    if policy.get("requires_human_approval_each_iteration") is not True:
        blocked.append("human_approval_each_iteration_required")
    max_iterations = int(policy.get("max_iterations") or 0)
    if max_iterations < 1 or max_iterations > 3:
        blocked.append("max_iterations_invalid")
    changed_files = list(policy.get("changed_files", []))
    if len(changed_files) != 1:
        blocked.append("single_changed_file_required")
    return blocked


def create_bounded_retry_recovery_metadata(
    *,
    bounded_loop_policy_path: str | Path,
    data_root: str | Path | None = None,
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    max_retries: int = 1,
    failure_classes: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    parsed = read_bounded_loop_policy_v1(policy_path=bounded_loop_policy_path, data_root=data_root)
    policy = parsed["policy"]
    policy_path = Path(bounded_loop_policy_path).expanduser().resolve()
    policy_dir = policy_path.parent
    root = Path(data_root if data_root is not None else policy_dir).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, policy_path, "bounded_loop_policy_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_policy(policy))
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if max_retries < 0 or max_retries > MAX_ALLOWED_RETRIES:
        blocked.append("max_retries_out_of_bounds")
    classes = list(dict.fromkeys(failure_classes or ["verification_failed", "transient_tool_failure"]))
    if not classes:
        blocked.append("failure_classes_required")
    invalid_classes = [value for value in classes if value not in _ALLOWED_FAILURE_CLASSES]
    if invalid_classes:
        blocked.append("failure_class_not_allowed")

    metadata_path = policy_dir / "bounded_retry_recovery.json"
    if not blocked:
        try:
            _ensure_under(policy_dir, metadata_path, "bounded_retry_recovery_outside_policy_dir")
        except ValueError as exc:
            blocked.append(str(exc))

    recovery_id = f"bounded_retry_recovery_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    base = {
        "status": "blocked" if blocked else ("planned" if dry_run else "created"),
        "recovery_id": recovery_id,
        "policy_id": policy.get("policy_id", ""),
        "transaction_id": policy.get("transaction_id", ""),
        "draft_pr_number": policy.get("draft_pr_number", 0),
        "changed_files": list(policy.get("changed_files", [])),
        "blocked_reasons": list(dict.fromkeys(blocked)),
        "metadata_path": str(metadata_path),
        "metadata_only": True,
        "max_retries": max_retries,
        "failure_classes": classes,
        "retry_execution_enabled": False,
        "failure_recovery_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "autonomous_execution_enabled": False,
        "requires_human_approval_before_retry": True,
    }
    if blocked or dry_run:
        return base

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc_now(),
        "bounded_loop_policy_path": str(policy_path),
        "allowed_recovery_actions": ["record_failure", "prepare_retry_plan", "request_human_approval"],
        "forbidden_recovery_actions": [
            "retry_without_human_approval",
            "retry_without_new_dry_run",
            "auto_continue",
            "execute_all",
            "runtime_escalation",
            "self_modify",
            "direct_merge",
        ],
        **base,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    policy["bounded_retry_recovery_status"] = "created"
    policy["bounded_retry_recovery_path"] = str(metadata_path)
    policy["retry_execution_enabled"] = False
    policy["failure_recovery_execution_enabled"] = False
    policy["auto_continue_enabled"] = False
    policy["execute_all_enabled"] = False
    policy["autonomous_execution_enabled"] = False
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    return base


def read_bounded_retry_recovery_metadata(*, metadata_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(metadata_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "bounded_retry_recovery_outside_data_root")
    return {"metadata": payload, "warnings": []}
