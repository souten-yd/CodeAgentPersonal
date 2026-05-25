from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.patch_transaction.v1"

DEFAULT_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".venv", "venv", "venv_sys", "tts_envs", "models", ".cache", "ca_data",
}

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$")
_DIFF_OLD_RE = re.compile(r"^---\s+(?:a/)?(.+)$")
_DIFF_NEW_RE = re.compile(r"^\+\+\+\s+(?:b/)?(.+)$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _safe_relpath(value: str) -> str:
    if not value:
        raise ValueError("empty_path_forbidden")
    p = Path(value)
    if p.is_absolute():
        raise ValueError("absolute_paths_forbidden")
    parts = p.parts
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("path_traversal_forbidden")
    return p.as_posix()


def _normalize_file_entry(project_root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    rel = str(entry.get("relative_path", "") or "")
    out = {
        "relative_path": rel,
        "change_type": str(entry.get("change_type", "unknown") or "unknown"),
        "old_path": entry.get("old_path"),
        "new_path": entry.get("new_path"),
        "size_before": entry.get("size_before"),
        "size_after": entry.get("size_after"),
        "sha256_before": entry.get("sha256_before"),
        "sha256_after": entry.get("sha256_after"),
        "exists_before": False,
        "path_valid": False,
        "warnings": warnings,
    }
    if out["change_type"] not in {"create", "modify", "delete", "rename", "unknown"}:
        out["change_type"] = "unknown"
        warnings.append("change_type_unknown")
    try:
        safe_rel = _safe_relpath(rel)
        out["relative_path"] = safe_rel
        top = safe_rel.split("/", 1)[0]
        if top in DEFAULT_EXCLUDED_DIRS:
            warnings.append("excluded_path")
        target = (project_root / safe_rel)
        _ensure_under(project_root, target, "project_escape")
        if target.exists() and target.is_symlink():
            warnings.append("symlink_path_skipped")
            out["path_valid"] = False
        else:
            out["exists_before"] = target.exists()
            out["path_valid"] = True
    except ValueError as exc:
        warnings.append(str(exc))
        out["path_valid"] = False
    return out


def _infer_paths_from_diff_text(diff_text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for line in diff_text.splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m:
            found.append({"relative_path": m.group(2), "change_type": "unknown"})
            continue
        m = _DIFF_NEW_RE.match(line)
        if m:
            path = m.group(1)
            if path != "/dev/null":
                found.append({"relative_path": path, "change_type": "unknown"})
            continue
        m = _DIFF_OLD_RE.match(line)
        if m:
            path = m.group(1)
            if path != "/dev/null":
                found.append({"relative_path": path, "change_type": "unknown"})
    seen: set[str] = set()
    uniq = []
    for e in found:
        if e["relative_path"] in seen:
            continue
        seen.add(e["relative_path"])
        uniq.append(e)
    return uniq


def create_rollback_metadata(*, snapshot_id: str = "", snapshot_manifest_path: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    warnings = []
    if not snapshot_id:
        warnings.append("snapshot_id_missing")
    if not snapshot_manifest_path:
        warnings.append("snapshot_manifest_path_missing")
    return {
        "rollback_strategy": "restore_snapshot_manual",
        "snapshot_id": snapshot_id,
        "snapshot_manifest_path": snapshot_manifest_path,
        "restore_supported": bool(snapshot_id or snapshot_manifest_path),
        "restore_manual_only": True,
        "automatic_rollback_enabled": False,
        "restore_plan_required": True,
        "notes": "Manual snapshot restore required; no automatic rollback.",
        "warnings": warnings,
    }


def create_patch_transaction(*, project_path: str | Path, data_root: str | Path, snapshot_id: str = "", snapshot_manifest_path: str = "", workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", reason: str = "", proposed_files: list[dict[str, Any]] | None = None, diff_text: str | None = None, diff_files: list[dict[str, Any]] | None = None, risk_class: str = "unknown", metadata: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve()
    transaction_id = f"txn_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    transaction_dir = root / "atlas" / "patch_transactions" / transaction_id
    warnings: list[str] = []
    entries = list(proposed_files or []) + list(diff_files or [])
    if diff_text:
        entries.extend(_infer_paths_from_diff_text(diff_text))
    normalized = [_normalize_file_entry(project_root, e) for e in entries]
    if not normalized:
        warnings.append("no_proposed_files")
    changed_file_count = sum(1 for e in normalized if e.get("path_valid"))
    diff_summary = {
        "total_files": len(normalized),
        "creates": sum(1 for e in normalized if e.get("change_type") == "create"),
        "modifies": sum(1 for e in normalized if e.get("change_type") == "modify"),
        "deletes": sum(1 for e in normalized if e.get("change_type") == "delete"),
        "renames": sum(1 for e in normalized if e.get("change_type") == "rename"),
        "unknown": sum(1 for e in normalized if e.get("change_type") == "unknown"),
        "warnings": warnings,
    }
    rb = create_rollback_metadata(snapshot_id=snapshot_id, snapshot_manifest_path=snapshot_manifest_path, data_root=root)
    if rb.get("warnings"):
        warnings.extend(rb["warnings"])
    created_at = _utc_now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "created_at": created_at,
        "project_path": str(project_root),
        "data_root": str(root),
        "workspace_id": workspace_id,
        "pool_id": pool_id,
        "item_id": item_id,
        "run_id": run_id,
        "reason": reason,
        "snapshot_id": snapshot_id,
        "snapshot_manifest_path": snapshot_manifest_path,
        "rollback_metadata": rb,
        "proposed_files": normalized,
        "diff_summary": diff_summary,
        "risk_class": risk_class or "unknown",
        "risk_metadata": {"status": "placeholder", "metadata": metadata or {}},
        "validation": {"dry_run": bool(dry_run), "path_safety": all(e.get("path_valid") for e in normalized) if normalized else True},
        "file_count": len(normalized),
        "changed_file_count": changed_file_count,
        "warnings": warnings,
        "apply_supported": False,
        "apply_status": "not_applied",
        "automatic_apply_enabled": False,
        "automatic_rollback_enabled": False,
        "autonomous_execution_enabled": False,
    }
    if not dry_run:
        transaction_dir.mkdir(parents=True, exist_ok=True)
        if diff_text is not None:
            diff_path = transaction_dir / "proposed.diff"
            _ensure_under(transaction_dir, diff_path, "diff_path_escape")
            diff_path.write_text(diff_text, encoding="utf-8")
            manifest["diff_text_path"] = str(diff_path)
        manifest_path = transaction_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    else:
        manifest_path = transaction_dir / "manifest.json"
        if diff_text is not None:
            manifest["diff_text_path"] = str(transaction_dir / "proposed.diff")
    return {
        "status": "planned" if dry_run else "created",
        "transaction_id": transaction_id,
        "transaction_dir": str(transaction_dir),
        "manifest_path": str(manifest_path),
        "project_path": str(project_root),
        "snapshot_id": snapshot_id,
        "file_count": len(normalized),
        "changed_file_count": changed_file_count,
        "warnings": warnings,
        "dry_run": bool(dry_run),
        "created_at": created_at,
    }


def read_patch_transaction_manifest(*, manifest_path: str | Path | None = None, transaction_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    if manifest_path is None:
        if not transaction_id or data_root is None:
            raise ValueError("manifest_locator_required")
        manifest = Path(data_root).resolve() / "atlas" / "patch_transactions" / transaction_id / "manifest.json"
    else:
        manifest = Path(manifest_path).expanduser().resolve()
    if not manifest.exists():
        raise ValueError("manifest_missing")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).expanduser().resolve()
    _ensure_under(root, manifest, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def validate_patch_transaction(*, manifest_path: str | Path | None = None, transaction_id: str = "", data_root: str | Path | None = None, project_path: str | Path | None = None) -> dict[str, Any]:
    parsed = read_patch_transaction_manifest(manifest_path=manifest_path, transaction_id=transaction_id, data_root=data_root)
    m = parsed["manifest"]
    warnings = list(parsed.get("warnings", []))
    errors: list[str] = []
    root = Path(data_root if data_root is not None else m["data_root"]).resolve()
    transaction_dir = Path(m.get("manifest_path") or Path(manifest_path) if manifest_path else root / "atlas" / "patch_transactions" / m["transaction_id"] / "manifest.json").resolve().parent
    try:
        _ensure_under(root, transaction_dir, "transaction_dir_outside_data_root")
    except ValueError as exc:
        errors.append(str(exc))
    project_root = Path(project_path if project_path is not None else m["project_path"]).resolve()
    path_safety_valid = True
    for entry in m.get("proposed_files", []):
        normalized = _normalize_file_entry(project_root, entry)
        if not normalized["path_valid"]:
            path_safety_valid = False
            warnings.extend(normalized["warnings"])
    diff_path = m.get("diff_text_path")
    if diff_path:
        try:
            _ensure_under(transaction_dir, Path(diff_path), "diff_path_outside_transaction_dir")
        except ValueError as exc:
            errors.append(str(exc))
    snapshot_ref_valid = bool(m.get("snapshot_id") or m.get("snapshot_manifest_path"))
    if not snapshot_ref_valid:
        warnings.append("snapshot_reference_missing")
    rollback_ready = bool(m.get("rollback_metadata")) and snapshot_ref_valid
    for key, expected in {
        "apply_supported": False,
        "automatic_apply_enabled": False,
        "automatic_rollback_enabled": False,
        "autonomous_execution_enabled": False,
    }.items():
        if m.get(key) is not expected:
            errors.append(f"{key}_must_be_false")
    valid = not errors and path_safety_valid
    return {
        "status": "validated",
        "transaction_id": m.get("transaction_id", ""),
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "rollback_ready": rollback_ready,
        "snapshot_reference_valid": snapshot_ref_valid,
        "path_safety_valid": path_safety_valid,
        "apply_supported": bool(m.get("apply_supported", False)),
        "automatic_apply_enabled": bool(m.get("automatic_apply_enabled", False)),
        "automatic_rollback_enabled": bool(m.get("automatic_rollback_enabled", False)),
    }


def summarize_patch_transaction(manifest: dict[str, Any], validation: dict[str, Any] | None = None) -> dict[str, Any]:
    v = validation or {}
    return {
        "transaction_id": manifest.get("transaction_id", ""),
        "status": manifest.get("apply_status", "not_applied"),
        "file_count": int(manifest.get("file_count", 0)),
        "risk_class": manifest.get("risk_class", "unknown"),
        "rollback_ready": bool(v.get("rollback_ready", bool(manifest.get("rollback_metadata")))),
        "warnings": list(dict.fromkeys((manifest.get("warnings", []) + v.get("warnings", [])))),
        "apply_supported": bool(manifest.get("apply_supported", False)),
        "automatic_apply_enabled": bool(manifest.get("automatic_apply_enabled", False)),
        "automatic_rollback_enabled": bool(manifest.get("automatic_rollback_enabled", False)),
    }


def build_latest_patch_transaction_workflow_metadata(*, data_root: str | Path, project_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    transaction_root = root / "atlas" / "patch_transactions"
    base = {
        "patch_transaction_available": False,
        "latest_patch_transaction_id": None,
        "patch_candidate_count": 0,
        "patch_transaction_source": "patch_transaction_preview_unavailable",
        "patch_transaction_preview_status": "missing",
        "patch_transaction_risk_class": "unknown",
        "patch_transaction_rollback_ready": False,
        "patch_transaction_apply_supported": False,
        "patch_transaction_automatic_apply_enabled": False,
        "patch_transaction_automatic_rollback_enabled": False,
        "patch_transaction_warnings": [],
    }
    try:
        _ensure_under(root, transaction_root, "transaction_root_outside_data_root")
    except ValueError as exc:
        return {**base, "patch_transaction_warnings": [str(exc)]}
    if not transaction_root.exists():
        return {**base, "patch_transaction_source": "no_patch_transactions_found"}

    project_filter = Path(project_path).expanduser().resolve() if project_path else None
    warnings: list[str] = []
    manifests = sorted(transaction_root.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for manifest_path in manifests:
        try:
            _ensure_under(transaction_root, manifest_path, "manifest_outside_patch_transaction_root")
            parsed = read_patch_transaction_manifest(manifest_path=manifest_path, data_root=root)
            manifest = parsed["manifest"]
            if project_filter is not None and Path(str(manifest.get("project_path", ""))).expanduser().resolve() != project_filter:
                continue
            validation = validate_patch_transaction(manifest_path=manifest_path, data_root=root, project_path=project_filter)
            summary = summarize_patch_transaction(manifest, validation)
            return {
                **base,
                "patch_transaction_available": True,
                "latest_patch_transaction_id": summary["transaction_id"],
                "patch_candidate_count": summary["file_count"],
                "patch_transaction_source": "latest_patch_transaction_manifest",
                "patch_transaction_preview_status": summary["status"],
                "patch_transaction_risk_class": summary["risk_class"],
                "patch_transaction_rollback_ready": summary["rollback_ready"],
                "patch_transaction_apply_supported": False,
                "patch_transaction_automatic_apply_enabled": False,
                "patch_transaction_automatic_rollback_enabled": False,
                "patch_transaction_warnings": summary["warnings"],
            }
        except Exception as exc:
            warnings.append(str(exc) or exc.__class__.__name__)
    return {**base, "patch_transaction_warnings": warnings[:5]}
