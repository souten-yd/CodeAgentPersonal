from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.atlas.draft_pr_creation import SCHEMA_VERSION as DRAFT_PR_RESULT_SCHEMA_VERSION, read_draft_pr_creation_result

SCHEMA_VERSION = "atlas.draft_pr_update_result.v1"
CONFIRMATION_TEXT = "UPDATE DRAFT PR"


class DraftPullRequestUpdateClient(Protocol):
    def update_pull_request(self, *, pr_number: int, title: str, body: str) -> dict[str, Any]: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _validate_creation_result(result: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if result.get("schema_version") != DRAFT_PR_RESULT_SCHEMA_VERSION:
        blocked.append("unsupported_draft_pr_result_schema")
    if result.get("status") != "created" or result.get("draft_pr_created") is not True:
        blocked.append("draft_pr_creation_result_required")
    if result.get("draft") is not True:
        blocked.append("draft_pr_must_be_draft")
    if not result.get("draft_pr_number"):
        blocked.append("draft_pr_number_required")
    if not result.get("draft_pr_url"):
        blocked.append("draft_pr_url_required")
    if result.get("push_performed") is not False:
        blocked.append("push_performed_must_be_false")
    if result.get("pr_update_enabled") is not False:
        blocked.append("pr_update_must_not_be_pre_enabled")
    if result.get("autonomous_execution_enabled") is not False:
        blocked.append("autonomous_execution_enabled_must_be_false")
    changed_files = list(result.get("changed_files", []))
    if len(changed_files) != 1:
        blocked.append("single_changed_file_required")
    return blocked


def _validate_client_response(response: dict[str, Any], expected_number: int) -> list[str]:
    blocked: list[str] = []
    if response.get("number") != expected_number:
        blocked.append("updated_pr_number_mismatch")
    if not (response.get("url") or response.get("html_url")):
        blocked.append("updated_pr_url_required")
    if response.get("draft") is not True:
        blocked.append("updated_pr_must_remain_draft")
    return blocked


def _build_update_body(result: dict[str, Any]) -> str:
    changed_files = ", ".join(str(path) for path in result.get("changed_files", []))
    return "\n".join(
        [
            "## Atlas Update",
            "- Updated from a manually approved draft PR creation result.",
            f"- Transaction: {result.get('transaction_id', '')}",
            f"- Changed files: {changed_files}",
            "",
            "## Safety",
            "- pr_update_enabled=false after this single approved update",
            "- push_performed=false",
            "- autonomous_execution_enabled=false",
            "- no retry, auto-continue, or execute-all is enabled",
        ]
    )


def create_manually_approved_pr_update(
    *,
    draft_pr_result_path: str | Path,
    data_root: str | Path | None = None,
    pr_client: DraftPullRequestUpdateClient | None = None,
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    title_prefix: str = "Atlas patch update",
    dry_run: bool = False,
) -> dict[str, Any]:
    parsed = read_draft_pr_creation_result(result_path=draft_pr_result_path, data_root=data_root)
    draft_result = parsed["result"]
    draft_path = Path(draft_pr_result_path).expanduser().resolve()
    draft_dir = draft_path.parent
    root = Path(data_root if data_root is not None else draft_dir).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, draft_path, "draft_pr_result_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    blocked.extend(_validate_creation_result(draft_result))
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if pr_client is None and not dry_run:
        blocked.append("pr_update_client_required")

    result_path = draft_dir / "draft_pr_update_result.json"
    if not blocked:
        try:
            _ensure_under(draft_dir, result_path, "pr_update_result_outside_draft_dir")
        except ValueError as exc:
            blocked.append(str(exc))

    pr_number = int(draft_result.get("draft_pr_number") or 0)
    update_id = f"draft_pr_update_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    title = f"{title_prefix}: {draft_result.get('transaction_id', '')}".strip()
    body = _build_update_body(draft_result)
    base = {
        "status": "blocked" if blocked else ("planned" if dry_run else "updated"),
        "update_id": update_id,
        "policy_id": draft_result.get("policy_id", ""),
        "proposal_id": draft_result.get("proposal_id", ""),
        "transaction_id": draft_result.get("transaction_id", ""),
        "blocked_reasons": list(dict.fromkeys(blocked)),
        "draft_pr_number": pr_number,
        "draft_pr_url": draft_result.get("draft_pr_url", ""),
        "changed_files": list(draft_result.get("changed_files", [])),
        "result_path": str(result_path),
        "dry_run": bool(dry_run),
        "pr_updated": False,
        "push_performed": False,
        "autonomous_execution_enabled": False,
        "confirmation_text_required": CONFIRMATION_TEXT,
    }
    if blocked or dry_run:
        return base

    assert pr_client is not None
    response = pr_client.update_pull_request(pr_number=pr_number, title=title, body=body)
    response_errors = _validate_client_response(response, pr_number)
    if response_errors:
        return {**base, "status": "blocked", "blocked_reasons": response_errors}

    update_result = {
        "schema_version": SCHEMA_VERSION,
        **base,
        "status": "updated",
        "created_at": _utc_now(),
        "pr_updated": True,
        "updated_pr_url": response.get("html_url") or response.get("url"),
        "updated_title": title,
        "updated_body": body,
        "draft": True,
    }
    result_path.write_text(json.dumps(update_result, indent=2), encoding="utf-8")
    draft_result["pr_update_status"] = "updated"
    draft_result["pr_update_result_path"] = str(result_path)
    draft_result["pr_updated_at"] = update_result["created_at"]
    draft_result["pr_update_enabled"] = False
    draft_result["push_performed"] = False
    draft_result["autonomous_execution_enabled"] = False
    draft_path.write_text(json.dumps(draft_result, indent=2), encoding="utf-8")
    return update_result


def read_draft_pr_update_result(*, result_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(result_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "draft_pr_update_result_outside_data_root")
    return {"result": payload, "warnings": []}
