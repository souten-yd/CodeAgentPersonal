from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.local_branch_proposal import BRANCH_CREATION_RESULT_SCHEMA_VERSION, read_local_branch_proposal

SCHEMA_VERSION = "atlas.draft_pr_policy.v1"
_ALLOWED_BASE_REFS = {"main", "master"}
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _read_branch_creation_result(*, result_path: str | Path, proposal_dir: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        path = _ensure_under(proposal_dir, Path(result_path).expanduser().resolve(), "branch_result_outside_proposal_dir")
    except ValueError as exc:
        return None, [str(exc)]
    if not path.exists():
        return None, ["branch_creation_result_missing"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != BRANCH_CREATION_RESULT_SCHEMA_VERSION:
        return payload, ["unsupported_branch_creation_result_schema"]
    if payload.get("status") != "created":
        return payload, ["branch_creation_result_not_created"]
    for key in ("checkout_performed", "commit_created", "draft_pr_creation_enabled", "autonomous_execution_enabled"):
        if payload.get(key) is not False:
            return payload, [f"{key}_must_be_false"]
    return payload, []


def create_draft_pr_policy_metadata(
    *,
    proposal_manifest_path: str | Path,
    data_root: str | Path | None = None,
    base_ref: str | None = None,
    title_prefix: str = "Atlas patch",
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    dry_run: bool = False,
) -> dict[str, Any]:
    parsed = read_local_branch_proposal(manifest_path=proposal_manifest_path, data_root=data_root)
    proposal = parsed["manifest"]
    root = Path(data_root if data_root is not None else proposal.get("data_root", "")).expanduser().resolve()
    proposal_path = Path(proposal_manifest_path).expanduser().resolve()
    proposal_dir = proposal_path.parent
    blocked: list[str] = []
    try:
        _ensure_under(root, proposal_path, "proposal_manifest_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")
    if proposal.get("branch_creation_status") != "created":
        blocked.append("branch_creation_required")
    if proposal.get("draft_pr_creation_enabled") is not False:
        blocked.append("draft_pr_creation_must_still_be_disabled")
    if proposal.get("autonomous_execution_enabled") is not False:
        blocked.append("autonomous_execution_must_be_disabled")

    result_path_value = proposal.get("branch_creation_result_path")
    branch_result: dict[str, Any] | None = None
    if not result_path_value:
        blocked.append("branch_creation_result_required")
    else:
        branch_result, result_errors = _read_branch_creation_result(result_path=result_path_value, proposal_dir=proposal_dir)
        blocked.extend(result_errors)

    target_base = base_ref or str(proposal.get("base_ref", ""))
    if target_base not in _ALLOWED_BASE_REFS:
        blocked.append("base_ref_not_allowed")
    branch_name = str(proposal.get("proposed_branch") or (branch_result or {}).get("branch_name") or "")
    if not branch_name or not _BRANCH_RE.match(branch_name) or branch_name in _ALLOWED_BASE_REFS:
        blocked.append("head_branch_invalid")
    changed_files = list(proposal.get("changed_files", []))
    if len(changed_files) != 1:
        blocked.append("single_changed_file_required")

    policy_id = f"draft_pr_policy_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    manifest_path_out = proposal_dir / "draft_pr_policy.json"
    if not blocked:
        try:
            _ensure_under(proposal_dir, manifest_path_out, "draft_pr_policy_outside_proposal_dir")
        except ValueError as exc:
            blocked.append(str(exc))

    base = {
        "status": "blocked" if blocked else ("planned" if dry_run else "created"),
        "policy_id": policy_id,
        "proposal_id": proposal.get("proposal_id", ""),
        "transaction_id": proposal.get("transaction_id", ""),
        "blocked_reasons": list(dict.fromkeys(blocked)),
        "base_ref": target_base,
        "head_branch": branch_name,
        "changed_files": changed_files,
        "manifest_path": str(manifest_path_out),
        "policy_only": True,
        "draft_pr_creation_enabled": False,
        "push_enabled": False,
        "pr_update_enabled": False,
        "autonomous_execution_enabled": False,
    }
    if blocked or dry_run:
        return base

    title = f"{title_prefix}: {proposal.get('transaction_id', '')}".strip()
    body_sections = [
        "## Summary",
        "- Draft PR policy metadata only; no PR is created by this step.",
        "- Requires the approved local branch creation artifact before PR creation can be considered.",
        "",
        "## Safety",
        "- draft_pr_creation_enabled=false",
        "- push_enabled=false",
        "- pr_update_enabled=false",
        "- autonomous_execution_enabled=false",
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": policy_id,
        "created_at": _utc_now(),
        "proposal_manifest_path": str(proposal_path),
        "branch_creation_result_path": str(result_path_value),
        "proposal_id": proposal.get("proposal_id", ""),
        "transaction_id": proposal.get("transaction_id", ""),
        "base_ref": target_base,
        "head_branch": branch_name,
        "changed_files": changed_files,
        "draft_pr_title": title,
        "draft_pr_body_template": "\n".join(body_sections),
        "policy_only": True,
        "draft_pr_creation_enabled": False,
        "push_enabled": False,
        "pr_update_enabled": False,
        "autonomous_execution_enabled": False,
        "manual_approval_required_for_draft_pr_creation": True,
        "next_required_action": "PR-ATLAS-SCALE-134 draft PR creation",
    }
    manifest_path_out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    proposal["draft_pr_policy_status"] = "created"
    proposal["draft_pr_policy_path"] = str(manifest_path_out)
    proposal["draft_pr_creation_enabled"] = False
    proposal["autonomous_execution_enabled"] = False
    proposal_path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    return base


def read_draft_pr_policy_metadata(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "draft_pr_policy_outside_data_root")
    return {"manifest": payload, "warnings": []}
