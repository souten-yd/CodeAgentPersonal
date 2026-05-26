from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.atlas.self_improvement_patch_apply import (
    SCHEMA_VERSION as APPLY_SCHEMA_VERSION,
    validate_self_improvement_patch_apply,
)

SCHEMA_VERSION = "atlas.self_improvement_draft_pr_creation.v1"
TRACK_PR = "PR-ATLAS-SCALE-145"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-146"
REQUIRED_CONFIRMATION_TEXT = "CREATE SELF IMPROVEMENT DRAFT PR"
_REQUIRED_APPLY_TRACK = "PR-ATLAS-SCALE-144"
_ALLOWED_BASE_REFS = {"main", "master"}
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class SelfImprovementDraftPullRequestClient(Protocol):
    def create_draft_pull_request(self, *, base_ref: str, head_branch: str, title: str, body: str) -> dict[str, Any]: ...


def create_self_improvement_draft_pr_one_action(
    *,
    apply_result_path: str | Path,
    data_root: str | Path,
    pr_client: SelfImprovementDraftPullRequestClient | None = None,
    base_ref: str = "main",
    head_branch: str = "",
    title: str = "Atlas self-improvement draft PR",
    body: str = "",
    branch_ready_for_draft_pr: bool = False,
    strict_gate_approved: bool = False,
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
    dry_run: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    root = Path(data_root).expanduser().resolve()
    apply_path = Path(apply_result_path).expanduser().resolve()
    blocked: list[str] = []
    try:
        _ensure_under(root, apply_path, "apply_result_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    apply_result = _load_apply_result(apply_path)
    blocked.extend(_validate_apply_result(apply_result))
    blocked.extend(_validate_refs(base_ref=base_ref, head_branch=head_branch, title=title, body=body))
    if not branch_ready_for_draft_pr:
        blocked.append("branch_ready_for_draft_pr_required")
    if not strict_gate_approved:
        blocked.append("strict_gate_approval_required")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != REQUIRED_CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if pr_client is None and not dry_run:
        blocked.append("draft_pr_client_required")

    creation_id = _creation_id(created)
    result_path = root / "atlas" / "self_improvement_draft_prs" / creation_id / "manifest.json"
    try:
        _ensure_under(root, result_path, "draft_pr_result_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    base = _base_result(
        creation_id=creation_id,
        apply_id=str(apply_result.get("apply_id", "")),
        transaction_id=str(apply_result.get("transaction_id", "")),
        status="blocked" if blocked else ("planned" if dry_run else "created"),
        blocked_reasons=list(dict.fromkeys(blocked)),
        base_ref=base_ref,
        head_branch=head_branch,
        changed_files=list(apply_result.get("changed_files", [])) if not blocked else [],
        result_path=str(result_path),
        dry_run=dry_run,
        title=title,
        body=body,
    )
    if blocked or dry_run:
        return validate_self_improvement_draft_pr_creation(base)

    assert pr_client is not None
    response = pr_client.create_draft_pull_request(base_ref=base_ref, head_branch=head_branch, title=title, body=body)
    response_errors = _validate_client_response(response)
    if response_errors:
        blocked_result = {**base, "status": "blocked", "blocked_reasons": response_errors, "changed_files": []}
        return validate_self_improvement_draft_pr_creation(blocked_result)

    result = {
        **base,
        "status": "created",
        "created_at": _utc_now(),
        "draft_pr_created": True,
        "draft_pr_number": response.get("number"),
        "draft_pr_url": response.get("html_url") or response.get("url"),
        "draft_pr_api_url": response.get("url") or "",
        "draft": True,
    }
    validated = validate_self_improvement_draft_pr_creation(result)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return validated


def load_self_improvement_draft_pr_creation(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "draft_pr_result_outside_data_root")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_self_improvement_draft_pr_creation(payload)


def validate_self_improvement_draft_pr_creation(result: dict[str, Any]) -> dict[str, Any]:
    required_false = [
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "self_modification_enabled",
        "self_apply_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "execution_performed",
        "patch_generated",
        "automatic_pr_creation_enabled",
        "draft_pr_updated",
        "verification_result_fabricated",
        "branch_created",
    ]
    status = result.get("status")
    invariants = {
        "schema_version": result.get("schema_version") == SCHEMA_VERSION,
        "track_pr": result.get("track_pr") == TRACK_PR,
        "next_required_pr": result.get("next_required_pr") == NEXT_REQUIRED_PR,
        "status": status in {"blocked", "planned", "created"},
        "single_action": result.get("single_action") is True,
        "manual_only": result.get("manual_only") is True,
        "approval_required": result.get("approval_required") is True,
        "confirmation_text_required": result.get("confirmation_text_required") == REQUIRED_CONFIRMATION_TEXT,
        "backend_authoritative": result.get("backend_authoritative") is True,
        "draft_pr_created": result.get("draft_pr_created") is (status == "created"),
        "blocked_reasons": status != "blocked" or bool(result.get("blocked_reasons")),
        "changed_files": status != "created" or len(result.get("changed_files", [])) == 1,
        "draft": status != "created" or result.get("draft") is True,
    }
    invariants.update({key: result.get(key) is False for key in required_false})
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return result


def _load_apply_result(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_self_improvement_patch_apply(payload)


def _validate_apply_result(apply_result: dict[str, Any]) -> list[str]:
    blocked: list[str] = []
    if apply_result.get("schema_version") != APPLY_SCHEMA_VERSION:
        blocked.append("unsupported_apply_schema")
    if apply_result.get("track_pr") != _REQUIRED_APPLY_TRACK:
        blocked.append("apply_track_required")
    if apply_result.get("next_required_pr") != TRACK_PR:
        blocked.append("apply_next_pr_required")
    if apply_result.get("status") != "applied":
        blocked.append("applied_self_improvement_patch_required")
    if apply_result.get("patch_applied") is not True:
        blocked.append("patch_applied_required")
    if apply_result.get("mutation_performed") is not True:
        blocked.append("mutation_performed_required")
    if len(apply_result.get("changed_files", [])) != 1:
        blocked.append("single_changed_file_required")
    for key in (
        "self_modification_enabled",
        "self_apply_enabled",
        "automatic_patch_generation_enabled",
        "automatic_patch_apply_enabled",
        "automatic_verification_enabled",
        "autonomous_execution_enabled",
        "autonomous_loop_execution_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "execution_performed",
        "patch_generated",
        "verification_result_fabricated",
        "branch_created",
        "draft_pr_created",
        "draft_pr_updated",
    ):
        if apply_result.get(key) is not False:
            blocked.append(f"{key}_must_be_false")
    return blocked


def _validate_refs(*, base_ref: str, head_branch: str, title: str, body: str) -> list[str]:
    blocked: list[str] = []
    if base_ref not in _ALLOWED_BASE_REFS:
        blocked.append("base_ref_not_allowed")
    if not head_branch or head_branch in _ALLOWED_BASE_REFS or not _BRANCH_RE.match(head_branch):
        blocked.append("head_branch_invalid")
    if not title.strip():
        blocked.append("draft_pr_title_required")
    if not body.strip():
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


def _base_result(
    *,
    creation_id: str,
    apply_id: str,
    transaction_id: str,
    status: str,
    blocked_reasons: list[str],
    base_ref: str,
    head_branch: str,
    changed_files: list[str],
    result_path: str,
    dry_run: bool,
    title: str,
    body: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "creation_id": creation_id,
        "track_pr": TRACK_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "apply_id": apply_id,
        "transaction_id": transaction_id,
        "status": status,
        "blocked_reasons": blocked_reasons,
        "base_ref": base_ref,
        "head_branch": head_branch,
        "changed_files": changed_files,
        "result_path": result_path,
        "dry_run": bool(dry_run),
        "draft_pr_title": title,
        "draft_pr_body": body,
        "single_action": True,
        "manual_only": True,
        "approval_required": True,
        "confirmation_text_required": REQUIRED_CONFIRMATION_TEXT,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "execution_performed": False,
        "patch_generated": False,
        "automatic_pr_creation_enabled": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
        "verification_result_fabricated": False,
        "branch_created": False,
    }


def _creation_id(created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"self_improvement_draft_pr_{created_norm}_{uuid.uuid4().hex[:8]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
