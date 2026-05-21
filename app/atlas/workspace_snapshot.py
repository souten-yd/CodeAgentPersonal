from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.workspace_snapshot.v1"

DEFAULT_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".venv", "venv", "venv_sys", "tts_envs", "models", ".cache", "ca_data",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_relpath(value: str) -> str:
    p = Path(value)
    if p.is_absolute():
        raise ValueError("absolute_paths_forbidden")
    parts = p.parts
    if any(part in ("..", "") for part in parts):
        raise ValueError("path_traversal_forbidden")
    return p.as_posix()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_project_file(project_root: Path, src: Path) -> Path:
    return _ensure_under(project_root, src, "project_escape")


def _is_symlink_or_symlink_parent(path: Path, project_root: Path) -> bool:
    project_root = project_root.resolve()
    target = path
    while True:
        if target.is_symlink():
            return True
        if target == project_root or target.parent == target:
            break
        target = target.parent
    return False


def _should_skip_snapshot_source(project_root: Path, src: Path) -> tuple[bool, str]:
    if _is_symlink_or_symlink_parent(src, project_root):
        try:
            _resolve_project_file(project_root, src)
            return True, "symlink_skipped"
        except ValueError:
            return True, "symlink_escape"
    try:
        _resolve_project_file(project_root, src)
    except ValueError:
        return True, "project_escape"
    return False, ""


def create_workspace_snapshot(*, project_path: str | Path, data_root: str | Path, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", reason: str = "", include_paths: list[str] | None = None, exclude_paths: list[str] | None = None, max_files: int | None = None, max_bytes: int | None = None, dry_run: bool = False) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve()
    snapshot_id = f"snap_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    snapshot_dir = root / "atlas" / "snapshots" / snapshot_id
    files_dir = snapshot_dir / "files"
    warnings: list[str] = []
    skipped_files: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    total_bytes = 0

    excludes = set(DEFAULT_EXCLUDED_DIRS)
    if exclude_paths:
        excludes.update(_safe_relpath(p).split("/")[0] for p in exclude_paths)
    include_rel = [_safe_relpath(p) for p in include_paths] if include_paths else []

    roots = [project_root / p for p in include_rel] if include_rel else [project_root]
    snapshots_root = (root / "atlas" / "snapshots").resolve()
    for base in roots:
        if base.is_absolute() and include_rel and str(base) not in [str(project_root / p) for p in include_rel]:
            warnings.append(f"include_path_invalid:{base}")
            continue
        try:
            _ensure_under(project_root, base, "include_path_escape")
        except ValueError:
            skipped_files.append({"relative_path": str(base), "reason": "symlink_escape" if base.is_symlink() else "include_path_escape"})
            warnings.append(f"include_path_escape:{base}")
            continue
        if _is_symlink_or_symlink_parent(base, project_root):
            skipped_files.append({"relative_path": str(base.relative_to(project_root)), "reason": "symlink_skipped"})
            warnings.append(f"include_path_symlink_skipped:{base}")
            continue
        if not base.exists():
            warnings.append(f"include_path_missing:{base}")
            continue
        candidates = [base] if base.is_file() else list(base.rglob("*"))
        for src in candidates:
            if src.is_dir():
                continue
            skip, reason = _should_skip_snapshot_source(project_root, src)
            if skip:
                rel = src.relative_to(project_root).as_posix() if src.is_relative_to(project_root) else str(src)
                skipped_files.append({"relative_path": rel, "reason": reason})
                continue
            resolved_src = src.resolve()
            if os.path.commonpath([str(snapshots_root), str(resolved_src)]) == str(snapshots_root):
                rel = src.relative_to(project_root).as_posix()
                skipped_files.append({"relative_path": rel, "reason": "snapshot_artifact_excluded"})
                continue
            rel = src.relative_to(project_root).as_posix()
            top = rel.split("/", 1)[0]
            if top in excludes:
                skipped_files.append({"relative_path": rel, "reason": "excluded"})
                continue
            if max_files is not None and len(files) >= max_files:
                skipped_files.append({"relative_path": rel, "reason": "max_files_exceeded"})
                continue
            size = src.stat().st_size
            if max_bytes is not None and total_bytes + size > max_bytes:
                skipped_files.append({"relative_path": rel, "reason": "max_bytes_exceeded"})
                continue
            total_bytes += size
            snap_rel = f"files/{rel}"
            entry = {
                "relative_path": rel,
                "snapshot_relative_path": snap_rel,
                "size_bytes": size,
                "sha256": _hash_file(src),
                "mtime_ns": getattr(src.stat(), "st_mtime_ns", None),
                "mode": stat.S_IMODE(src.stat().st_mode),
            }
            files.append(entry)
            if not dry_run:
                dst = files_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    created_at = _utc_now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "created_at": created_at,
        "project_path": str(project_root),
        "data_root": str(root),
        "workspace_id": workspace_id,
        "pool_id": pool_id,
        "item_id": item_id,
        "run_id": run_id,
        "reason": reason,
        "files": files,
        "skipped_files": skipped_files,
        "file_count": len(files),
        "skipped_count": len(skipped_files),
        "total_bytes": total_bytes,
        "hash_algorithm": "sha256",
        "restore_supported": True,
        "restore_status": "manual_only",
        "symlink_policy": "skip",
        "path_safety": "project_root_resolved_paths_only",
        "delete_missing_before_supported": False,
        "warnings": warnings,
    }
    if not dry_run:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "status": "planned" if dry_run else "created",
        "snapshot_id": snapshot_id,
        "snapshot_dir": str(snapshot_dir),
        "manifest_path": str(snapshot_dir / "manifest.json"),
        "project_path": str(project_root),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "skipped_count": len(skipped_files),
        "skipped_files": skipped_files,
        "warnings": warnings,
        "dry_run": dry_run,
        "created_at": created_at,
    }


def read_workspace_snapshot_manifest(*, manifest_path: str | Path | None = None, snapshot_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    if manifest_path is None:
        if not snapshot_id or data_root is None:
            raise ValueError("manifest_locator_required")
        manifest = Path(data_root).resolve() / "atlas" / "snapshots" / snapshot_id / "manifest.json"
    else:
        manifest = Path(manifest_path).expanduser().resolve()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).expanduser().resolve()
    _ensure_under(root, manifest, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def plan_workspace_restore(*, manifest_path: str | Path | None = None, snapshot_id: str = "", data_root: str | Path | None = None, project_path: str | Path, delete_missing_before: bool = False) -> dict[str, Any]:
    manifest = read_workspace_snapshot_manifest(manifest_path=manifest_path, snapshot_id=snapshot_id, data_root=data_root)["manifest"]
    project_root = Path(project_path).expanduser().resolve()
    restore, create, overwrite, changed = [], [], [], []
    snapshot_set = set()
    for entry in manifest["files"]:
        rel = _safe_relpath(entry["relative_path"])
        snapshot_set.add(rel)
        tgt = project_root / rel
        restore.append(rel)
        if not tgt.exists():
            create.append(rel)
            continue
        if _hash_file(tgt) != entry["sha256"]:
            overwrite.append(rel)
            changed.append(rel)
    files_missing = []
    warnings = []
    if delete_missing_before:
        warnings.append("delete_missing_before_plan_only")
        for p in project_root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(project_root).as_posix()
                if rel not in snapshot_set:
                    files_missing.append(rel)
    return {"status": "planned", "snapshot_id": manifest["snapshot_id"], "restore_plan": {"delete_missing_before": delete_missing_before, "delete_missing_before_executed": False}, "files_to_restore": restore, "files_to_create": create, "files_to_overwrite": overwrite, "files_missing_from_snapshot": files_missing, "files_changed_since_snapshot": changed, "warnings": warnings}


def restore_workspace_snapshot(*, manifest_path: str | Path | None = None, snapshot_id: str = "", data_root: str | Path | None = None, project_path: str | Path, confirm_restore: bool, delete_missing_before: bool = False) -> dict[str, Any]:
    manifest = read_workspace_snapshot_manifest(manifest_path=manifest_path, snapshot_id=snapshot_id, data_root=data_root)["manifest"]
    if not confirm_restore:
        return {"status": "blocked", "snapshot_id": manifest["snapshot_id"], "restored_count": 0, "skipped_count": len(manifest["files"]), "report_path": "", "warnings": ["confirmation_required"]}
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root if data_root else manifest["data_root"]).expanduser().resolve()
    snapshot_dir = root / "atlas" / "snapshots" / manifest["snapshot_id"]
    restored = 0
    skipped = 0
    warnings = []
    if delete_missing_before:
        warnings.append("delete_missing_before_not_destructive")
    for entry in manifest["files"]:
        try:
            rel = _safe_relpath(entry["relative_path"])
            snap_rel = _safe_relpath(entry["snapshot_relative_path"])
            raw_src = snapshot_dir / snap_rel
            if raw_src.is_symlink():
                skipped += 1
                warnings.append(f"symlink_restore_source_skipped:{snap_rel}")
                continue
            src = _ensure_under(snapshot_dir, raw_src, "snapshot_escape")
            if not src.exists() or not src.is_file():
                skipped += 1
                warnings.append(f"snapshot_source_missing_or_not_file:{snap_rel}")
                continue
            dst = _ensure_under(project_root, project_root / rel, "project_escape")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            restored += 1
        except Exception as exc:
            skipped += 1
            warnings.append(str(exc))
    report_dir = root / "atlas" / "snapshots" / "restore_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"restore_{manifest['snapshot_id']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report = {"snapshot_id": manifest["snapshot_id"], "restored_count": restored, "skipped_count": skipped, "warnings": warnings, "delete_missing_before": delete_missing_before, "delete_missing_before_requested": delete_missing_before, "delete_missing_before_executed": False, "manual_only": True, "automatic_rollback_enabled": False, "path_safety": "snapshot_and_project_bounds_checked"}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"status": "restored", "snapshot_id": manifest["snapshot_id"], "restored_count": restored, "skipped_count": skipped, "report_path": str(report_path), "warnings": warnings}
