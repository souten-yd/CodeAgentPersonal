from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field


WORKSPACE_POLICY_SCHEMA_VERSION = "atlas.play.workspace_policy.v1"

PROTECTED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".cache",
    "ca_data",
}


class WorkspacePermission(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    SERVE = "serve"


class StrictPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceAccessDecision(StrictPolicyModel):
    schema_version: str = WORKSPACE_POLICY_SCHEMA_VERSION
    allowed: bool
    permission: WorkspacePermission
    relative_path: str
    resolved_path: str = ""
    reason: str = ""
    protected_directory: str = ""
    symlink_escape_checked: bool = True


def _decode_path(value: str) -> str:
    decoded = str(value or "").strip()
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded.replace("\\", "/")


def _is_under(root: Path, target: Path) -> bool:
    try:
        return os.path.commonpath([str(root), str(target)]) == str(root)
    except ValueError:
        return False


def normalize_workspace_relative_path(value: str, *, allow_root: bool = False) -> str:
    decoded = _decode_path(value)
    if decoded in {"", "."} and allow_root:
        return "."
    if decoded in {"", "."}:
        raise ValueError("empty_path")
    win = PureWindowsPath(decoded)
    if decoded.startswith("/") or win.drive or win.root:
        raise ValueError("absolute_path_forbidden")
    if "//" in decoded:
        raise ValueError("path_traversal_forbidden")
    parts = Path(decoded).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path_traversal_forbidden")
    return Path(*parts).as_posix()


def _protected_part(relative_path: str) -> str:
    parts = [part.lower() for part in Path(relative_path).parts if part not in {"", "."}]
    for part in parts:
        if part in PROTECTED_DIRECTORY_NAMES:
            return part
    return ""


def _has_symlink_escape(root: Path, target: Path) -> bool:
    current = target
    existing_parts: list[Path] = []
    while current != root and current != current.parent:
        if current.exists():
            existing_parts.append(current)
        current = current.parent
    for part in existing_parts:
        if part.is_symlink():
            try:
                if not _is_under(root, part.resolve()):
                    return True
            except OSError:
                return True
    return False


def decide_workspace_access(
    *,
    project_root: str | Path,
    relative_path: str,
    permission: WorkspacePermission | str,
    allow_root: bool = False,
) -> WorkspaceAccessDecision:
    permission_value = WorkspacePermission(permission)
    try:
        safe_rel = normalize_workspace_relative_path(relative_path, allow_root=allow_root)
    except ValueError as exc:
        return WorkspaceAccessDecision(
            allowed=False,
            permission=permission_value,
            relative_path=str(relative_path or ""),
            reason=str(exc),
        )

    protected = _protected_part(safe_rel)
    if protected:
        return WorkspaceAccessDecision(
            allowed=False,
            permission=permission_value,
            relative_path=safe_rel,
            reason="protected_directory",
            protected_directory=protected,
        )

    root = Path(project_root).expanduser().resolve()
    target = root if safe_rel == "." else (root / safe_rel).resolve(strict=False)
    if not _is_under(root, target):
        return WorkspaceAccessDecision(
            allowed=False,
            permission=permission_value,
            relative_path=safe_rel,
            resolved_path=str(target),
            reason="path_escape",
        )
    if _has_symlink_escape(root, target):
        return WorkspaceAccessDecision(
            allowed=False,
            permission=permission_value,
            relative_path=safe_rel,
            resolved_path=str(target),
            reason="symlink_escape",
        )
    return WorkspaceAccessDecision(
        allowed=True,
        permission=permission_value,
        relative_path=safe_rel,
        resolved_path=str(target),
    )


class WorkspaceFileEntry(StrictPolicyModel):
    schema_version: str = WORKSPACE_POLICY_SCHEMA_VERSION
    relative_path: str
    kind: str = Field(pattern="^(file|directory)$")
    size_bytes: int = 0
    sha256: str = ""
    writable: bool = False
    executable: bool = False
    servable: bool = False
