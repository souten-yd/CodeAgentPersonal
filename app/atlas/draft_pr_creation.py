from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.atlas.draft_pr_policy import SCHEMA_VERSION as POLICY_SCHEMA_VERSION, read_draft_pr_policy_metadata

SCHEMA_VERSION = "atlas.draft_pr_creation_result.v1"
CONFIRMATION_TEXT = "CREATE DRAFT PR"
_ALLOWED_BASE_REFS = {"main", "master"}
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class DraftPullRequestClient(Protocol):
    def create_draft_pull_request(self, *, base_ref: str, head_branch: str, title: str, body: str) -> dict[str, Any]: ...


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
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        blocked.append("unsupported_policy_schema")
    if policy.get("policy_only") is not True:
        blocked.append("policy_only_required")
    if policy.get("draft_pr_creation_enabled") is not False:
        blocked.append("policy_must_not_pre_enable_draft_pr_creation")
    for key in ("push_enabled", "pr_update_enabled", "autonomous_execution_enabled"):
        if policy.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    if policy.get("manual_approval_required_for_draft_pr_creation") is not True:
        blocked.append("manual_approval_policy_required")
    base_ref = str(policy.get("base_ref", ""))
    if base_ref not in _ALLOWED_BASE_REFS:
        blocked.append("base_ref_not_allowed")
    head_branch = str(policy.get("head_branch", ""))
    if not head_branch or head_branch in _ALLOWED_BASE_REFS or not _BRANCH_RE.match(head_branch):
        blocked.append("head_branch_invalid")
    changed_files = list(policy.get("changed_files", []))
    if len(changed_files) != 1:
        blocked.append("single_changed_file_required")
    title = str(policy.get("draft_pr_title", "")).strip()
    body = str(policy.get("draft_pr_body_template", "")).strip()
    if not title:
        blocked.append("draft_pr_title_required")
    if not body:
        blocked.append("draft_pr_body_required")
    return blocked


def _validate_client_response(response: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if not response.get("number"):
        blocked.append("draft_pr_number_required")
    if not (response.get("url") or response.get("html_url")):
        blocked.append("draft_pr_url_required")
    if response.get("draft") is not True:
        blocked.append("draft_pr_must_be_draft")
    return blocked


def create_manually_approved_draft_pr(
    *,
    policy_manifest_path: str | Path,
    data_root: str | Path | None = None,
    pr_client: DraftPullRequestClient | None = None,
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    parsed = read_draft_pr_policy_metadata(manifest_path=policy_manifest_path, data_root=data_root)
    policy = parsed["manifest"]
    policy_path = Path(policy_manifest_path).expanduser().resolve()
    policy_dir = policy_path.parent
    root = Path(data_root if data_root is not None else policy_dir).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, policy_path, "draft_pr_policy_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_policy(policy))
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if pr_client is None and not dry_run:
        blocked.append("draft_pr_client_required")

    result_path = policy_dir / "draft_pr_creation_result.json"
    if not blocked:
        try:
            _ensure_under(policy_dir, result_path, "draft_pr_result_outside_policy_dir")
        except ValueError as exc:
            blocked.append(str(exc))

    base = {
        "status": "blocked" if blocked else ("planned" if dry_run else "created"),
        "policy_id": policy.get("policy_id", ""),
        "proposal_id": policy.get("proposal_id", ""),
        "transaction_id": policy.get("transaction_id", ""),
        "blocked_reasons": list(dict.fromkeys(blocked)),
        "base_ref": policy.get("base_ref", ""),
        "head_branch": policy.get("head_branch", ""),
        "changed_files": list(policy.get("changed_files", [])),
        "result_path": str(result_path),
        "dry_run": bool(dry_run),
        "draft_pr_created": False,
        "push_performed": False,
        "pr_update_enabled": False,
        "autonomous_execution_enabled": False,
        "confirmation_text_required": CONFIRMATION_TEXT,
    }
    if blocked or dry_run:
        return base

    assert pr_client is not None
    response = pr_client.create_draft_pull_request(
        base_ref=str(policy["base_ref"]),
        head_branch=str(policy["head_branch"]),
        title=str(policy["draft_pr_title"]),
        body=str(policy["draft_pr_body_template"]),
    )
    response_errors = _validate_client_response(response)
    if response_errors:
        return {**base, "status": "blocked", "blocked_reasons": response_errors}

    result = {
        "schema_version": SCHEMA_VERSION,
        **base,
        "status": "created",
        "created_at": _utc_now(),
        "draft_pr_created": True,
        "draft_pr_number": response.get("number"),
        "draft_pr_url": response.get("html_url") or response.get("url"),
        "draft_pr_api_url": response.get("url") or "",
        "draft": True,
    }
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    policy["draft_pr_creation_status"] = "created"
    policy["draft_pr_creation_result_path"] = str(result_path)
    policy["draft_pr_created_at"] = result["created_at"]
    policy["draft_pr_creation_enabled"] = False
    policy["push_enabled"] = False
    policy["pr_update_enabled"] = False
    policy["autonomous_execution_enabled"] = False
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    return result


def read_draft_pr_creation_result(*, result_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(result_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "draft_pr_result_outside_data_root")
    return {"result": payload, "warnings": []}
