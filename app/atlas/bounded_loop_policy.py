from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.draft_pr_update import SCHEMA_VERSION as PR_UPDATE_RESULT_SCHEMA_VERSION, read_draft_pr_update_result

SCHEMA_VERSION = "atlas.bounded_loop_policy.v1"
MAX_ALLOWED_ITERATIONS = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _validate_pr_update_result(result: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if result.get("schema_version") != PR_UPDATE_RESULT_SCHEMA_VERSION:
        blocked.append("unsupported_pr_update_result_schema")
    if result.get("status") != "updated" or result.get("pr_updated") is not True:
        blocked.append("pr_update_result_required")
    if result.get("draft") is not True:
        blocked.append("draft_pr_required")
    if not result.get("draft_pr_number"):
        blocked.append("draft_pr_number_required")
    if result.get("push_performed") is not False:
        blocked.append("push_performed_must_be_false")
    if result.get("autonomous_execution_enabled") is not False:
        blocked.append("autonomous_execution_enabled_must_be_false")
    changed_files = list(result.get("changed_files", []))
    if len(changed_files) != 1:
        blocked.append("single_changed_file_required")
    return blocked


def create_bounded_loop_policy_v1(
    *,
    pr_update_result_path: str | Path,
    data_root: str | Path | None = None,
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    max_iterations: int = 1,
    dry_run: bool = False,
) -> dict[str, Any]:
    parsed = read_draft_pr_update_result(result_path=pr_update_result_path, data_root=data_root)
    pr_update = parsed["result"]
    update_path = Path(pr_update_result_path).expanduser().resolve()
    update_dir = update_path.parent
    root = Path(data_root if data_root is not None else update_dir).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, update_path, "pr_update_result_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_pr_update_result(pr_update))
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if max_iterations < 1 or max_iterations > MAX_ALLOWED_ITERATIONS:
        blocked.append("max_iterations_out_of_bounds")

    policy_path = update_dir / "bounded_loop_policy.json"
    if not blocked:
        try:
            _ensure_under(update_dir, policy_path, "bounded_loop_policy_outside_update_dir")
        except ValueError as exc:
            blocked.append(str(exc))

    policy_id = f"bounded_loop_policy_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    base = {
        "status": "blocked" if blocked else ("planned" if dry_run else "created"),
        "policy_id": policy_id,
        "update_id": pr_update.get("update_id", ""),
        "transaction_id": pr_update.get("transaction_id", ""),
        "draft_pr_number": pr_update.get("draft_pr_number", 0),
        "changed_files": list(pr_update.get("changed_files", [])),
        "blocked_reasons": list(dict.fromkeys(blocked)),
        "policy_path": str(policy_path),
        "policy_only": True,
        "max_iterations": max_iterations,
        "loop_execution_enabled": False,
        "bounded_retry_enabled": False,
        "autonomous_execution_enabled": False,
        "self_modification_enabled": False,
        "requires_human_approval_each_iteration": True,
    }
    if blocked or dry_run:
        return base

    policy = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc_now(),
        "pr_update_result_path": str(update_path),
        "allowed_inputs": ["approved_pr_update_result"],
        "allowed_iteration_actions": ["read_status", "prepare_next_plan", "request_human_approval"],
        "forbidden_iteration_actions": [
            "execute_without_human_approval",
            "retry_without_policy",
            "auto_continue",
            "execute_all",
            "self_modify",
            "runtime_escalation",
            "vue_authoritative_execution",
        ],
        **base,
    }
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    pr_update["bounded_loop_policy_status"] = "created"
    pr_update["bounded_loop_policy_path"] = str(policy_path)
    pr_update["loop_execution_enabled"] = False
    pr_update["bounded_retry_enabled"] = False
    pr_update["autonomous_execution_enabled"] = False
    update_path.write_text(json.dumps(pr_update, indent=2), encoding="utf-8")
    return base


def read_bounded_loop_policy_v1(*, policy_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(policy_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "bounded_loop_policy_outside_data_root")
    return {"policy": payload, "warnings": []}
