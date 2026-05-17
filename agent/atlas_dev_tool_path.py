from __future__ import annotations

from pathlib import Path


def validate_relative_path(path: str) -> str:
    p = str(path or "").strip().replace("\\", "/")
    if p in {"", "."}:
        return ""
    if p.startswith("/") or p.startswith("~"):
        raise ValueError("absolute/home path is not allowed")
    parts = [part for part in p.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ValueError("parent traversal is not allowed")
    return "/".join(parts)


def resolve_project_root(project_path: str) -> Path:
    if not project_path:
        raise ValueError("project_path is required")
    if str(project_path).startswith("~"):
        raise ValueError("home expansion is not allowed")
    root = Path(project_path).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("project_path must point to an existing directory")
    return root


def ensure_under_project(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except Exception as exc:
        raise ValueError("path escapes project root") from exc
    return resolved
