from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.patch_transaction import read_patch_transaction_manifest, validate_patch_transaction

SCHEMA_VERSION = "atlas.local_branch_proposal.v1"
_BRANCH_SAFE_RE = re.compile(r"[^a-zA-Z0-9._/-]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _safe_branch_segment(value: str) -> str:
    cleaned = _BRANCH_SAFE_RE.sub("-", value.strip()).strip("./-")
    cleaned = re.sub(r"-+", "-", cleaned)
    return cleaned[:80] or "patch-transaction"


def _read_apply_result(transaction_dir: Path, value: str | Path | None) -> tuple[dict[str, Any] | None, list[str]]:
    if value is None:
        candidate = transaction_dir / "apply_result.json"
    else:
        candidate = Path(value).expanduser().resolve()
    try:
        path = _ensure_under(transaction_dir, candidate, "apply_result_outside_transaction_dir")
    except ValueError as exc:
        return None, [str(exc)]
    if not path.exists():
        return None, ["apply_result_missing"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "applied":
        return payload, ["apply_result_status_not_applied"]
    for key in ("automatic_apply_enabled", "automatic_rollback_enabled", "autonomous_execution_enabled"):
        if payload.get(key) is not False:
            return payload, [f"{key}_must_be_false"]
    return payload, []


def create_local_branch_proposal(
    *,
    manifest_path: str | Path | None = None,
    transaction_id: str = "",
    data_root: str | Path | None = None,
    project_path: str | Path | None = None,
    apply_result_path: str | Path | None = None,
    base_ref: str = "main",
    base_sha: str = "",
    branch_prefix: str = "atlas/",
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    dry_run: bool = False,
) -> dict[str, Any]:
    parsed = read_patch_transaction_manifest(manifest_path=manifest_path, transaction_id=transaction_id, data_root=data_root)
    patch_manifest = parsed["manifest"]
    txn_id = str(patch_manifest.get("transaction_id", ""))
    root = Path(data_root if data_root is not None else patch_manifest.get("data_root", "")).expanduser().resolve()
    if manifest_path is None:
        transaction_dir = root / "atlas" / "patch_transactions" / txn_id
    else:
        transaction_dir = Path(manifest_path).expanduser().resolve().parent
    blocked: list[str] = []
    try:
        _ensure_under(root, transaction_dir, "transaction_dir_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    validation = validate_patch_transaction(
        manifest_path=manifest_path,
        transaction_id=transaction_id,
        data_root=root,
        project_path=project_path,
    )
    if not validation.get("valid"):
        blocked.append("transaction_validation_failed")
    if not validation.get("snapshot_reference_valid"):
        blocked.append("snapshot_reference_required")
    if not validation.get("rollback_ready"):
        blocked.append("rollback_ready_required")
    if approval_status != "approved" or explicit_decision != "approve":
        blocked.append("explicit_human_approval_required")

    apply_result, apply_errors = _read_apply_result(transaction_dir, apply_result_path)
    blocked.extend(apply_errors)
    changed_files = list(apply_result.get("changed_files", [])) if apply_result else []
    if len(changed_files) != 1:
        blocked.append("single_applied_file_required")

    proposal_id = f"branch_proposal_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    safe_txn = _safe_branch_segment(txn_id.removeprefix("txn_"))
    safe_prefix = branch_prefix.strip().strip("/")
    if not safe_prefix:
        safe_prefix = "atlas"
    proposed_branch = f"{safe_prefix}/patch-{safe_txn}"
    proposal_dir = root / "atlas" / "branch_proposals" / proposal_id
    try:
        _ensure_under(root, proposal_dir, "proposal_dir_outside_data_root")
    except ValueError as exc:
        blocked.append(str(exc))

    base = {
        "status": "blocked" if blocked else ("planned" if dry_run else "created"),
        "proposal_id": proposal_id,
        "transaction_id": txn_id,
        "blocked_reasons": list(dict.fromkeys(blocked)),
        "proposal_dir": str(proposal_dir),
        "manifest_path": str(proposal_dir / "manifest.json"),
        "proposed_branch": proposed_branch,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "changed_files": changed_files,
        "proposal_only": True,
        "branch_creation_supported": False,
        "git_mutation_enabled": False,
        "draft_pr_creation_enabled": False,
        "autonomous_execution_enabled": False,
    }
    if blocked or dry_run:
        return base

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": proposal_id,
        "created_at": _utc_now(),
        "transaction_id": txn_id,
        "patch_transaction_manifest_path": str(Path(manifest_path).expanduser().resolve()) if manifest_path is not None else str(transaction_dir / "manifest.json"),
        "apply_result_path": str(Path(apply_result_path).expanduser().resolve()) if apply_result_path is not None else str(transaction_dir / "apply_result.json"),
        "project_path": str(Path(project_path if project_path is not None else patch_manifest.get("project_path", "")).expanduser().resolve()),
        "data_root": str(root),
        "base_ref": base_ref,
        "base_sha": base_sha,
        "proposed_branch": proposed_branch,
        "changed_files": changed_files,
        "proposal_only": True,
        "branch_creation_supported": False,
        "branch_creation_status": "not_created",
        "git_mutation_enabled": False,
        "draft_pr_creation_enabled": False,
        "autonomous_execution_enabled": False,
        "manual_approval_required_for_branch_creation": True,
        "next_required_action": "PR-ATLAS-SCALE-132 approved local branch creation",
    }
    proposal_dir.mkdir(parents=True, exist_ok=True)
    manifest_path_out = proposal_dir / "manifest.json"
    _ensure_under(proposal_dir, manifest_path_out, "proposal_manifest_outside_proposal_dir")
    manifest_path_out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return base


def read_local_branch_proposal(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).expanduser().resolve()
    _ensure_under(root, path, "proposal_manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}
