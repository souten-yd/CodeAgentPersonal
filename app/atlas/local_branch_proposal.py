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
BRANCH_CREATION_RESULT_SCHEMA_VERSION = "atlas.local_branch_creation_result.v1"
_BRANCH_SAFE_RE = re.compile(r"[^a-zA-Z0-9._/-]+")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
CONFIRMATION_TEXT = "CREATE LOCAL BRANCH"


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


def _validate_branch_name(value: str) -> list[str]:
    errors: list[str] = []
    if not value or value.strip() != value:
        errors.append("branch_name_invalid")
    if value.startswith(("/", ".")) or value.endswith(("/", ".", ".lock")):
        errors.append("branch_name_invalid")
    if ".." in value or "//" in value or "@{" in value or "\\" in value:
        errors.append("branch_name_invalid")
    if any(ch.isspace() or ch in "~^:?*[" for ch in value):
        errors.append("branch_name_invalid")
    if any(part in {"", ".", ".."} or part.endswith(".lock") for part in value.split("/")):
        errors.append("branch_name_invalid")
    return errors


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


def _branch_exists(git_dir: Path, branch_name: str) -> bool:
    ref_path = git_dir / "refs" / "heads" / branch_name
    if ref_path.exists():
        return True
    packed_refs = git_dir / "packed-refs"
    if not packed_refs.exists():
        return False
    needle = f" refs/heads/{branch_name}"
    for line in packed_refs.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("#") or line.startswith("^"):
            continue
        if line.endswith(needle):
            return True
    return False


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


def create_approved_local_branch(
    *,
    proposal_manifest_path: str | Path,
    data_root: str | Path | None = None,
    project_path: str | Path | None = None,
    approval_status: str = "missing",
    explicit_decision: str = "unknown",
    confirmation_token_present: bool = False,
    confirmation_text: str = "",
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
    if not confirmation_token_present:
        blocked.append("confirmation_token_required")
    if confirmation_text != CONFIRMATION_TEXT:
        blocked.append("confirmation_text_mismatch")
    if proposal.get("proposal_only") is not True:
        blocked.append("proposal_only_required")
    if proposal.get("branch_creation_status") != "not_created":
        blocked.append("branch_creation_status_not_ready")
    for key in ("git_mutation_enabled", "draft_pr_creation_enabled", "autonomous_execution_enabled"):
        if proposal.get(key) is not False:
            blocked.append(f"{key}_must_be_false")

    branch_name = str(proposal.get("proposed_branch", ""))
    blocked.extend(_validate_branch_name(branch_name))
    base_sha = str(proposal.get("base_sha", ""))
    if not _SHA_RE.match(base_sha):
        blocked.append("base_sha_required")
    changed_files = list(proposal.get("changed_files", []))
    if len(changed_files) != 1:
        blocked.append("single_changed_file_required")

    project_root = Path(project_path if project_path is not None else proposal.get("project_path", "")).expanduser().resolve()
    git_dir = project_root / ".git"
    if not git_dir.exists() or not git_dir.is_dir():
        blocked.append("git_dir_missing")
    else:
        try:
            _ensure_under(project_root, git_dir, "git_dir_outside_project")
        except ValueError as exc:
            blocked.append(str(exc))
        if _branch_exists(git_dir, branch_name):
            blocked.append("branch_already_exists")

    result_path = proposal_dir / "branch_creation_result.json"
    if not blocked:
        try:
            _ensure_under(proposal_dir, result_path, "branch_result_outside_proposal_dir")
        except ValueError as exc:
            blocked.append(str(exc))

    base = {
        "status": "blocked" if blocked else ("planned" if dry_run else "created"),
        "proposal_id": proposal.get("proposal_id", ""),
        "transaction_id": proposal.get("transaction_id", ""),
        "blocked_reasons": list(dict.fromkeys(blocked)),
        "branch_name": branch_name,
        "base_ref": proposal.get("base_ref", ""),
        "base_sha": base_sha,
        "changed_files": changed_files,
        "dry_run": bool(dry_run),
        "checkout_performed": False,
        "commit_created": False,
        "draft_pr_creation_enabled": False,
        "autonomous_execution_enabled": False,
        "confirmation_text_required": CONFIRMATION_TEXT,
    }
    if blocked or dry_run:
        return base

    assert git_dir.exists()
    ref_path = _ensure_under(git_dir / "refs" / "heads", git_dir / "refs" / "heads" / branch_name, "branch_ref_outside_heads")
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(f"{base_sha.lower()}\n", encoding="ascii")
    result = {**base, "status": "created", "created_at": _utc_now(), "ref_path": str(ref_path)}
    result_path.write_text(json.dumps({"schema_version": BRANCH_CREATION_RESULT_SCHEMA_VERSION, **result}, indent=2), encoding="utf-8")

    proposal["branch_creation_status"] = "created"
    proposal["branch_creation_result_path"] = str(result_path)
    proposal["branch_created_at"] = result["created_at"]
    proposal["branch_creation_supported"] = True
    proposal["git_mutation_enabled"] = False
    proposal["draft_pr_creation_enabled"] = False
    proposal["autonomous_execution_enabled"] = False
    proposal_path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    result["result_path"] = str(result_path)
    return result
