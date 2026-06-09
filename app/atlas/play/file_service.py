from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.atlas.play.contracts import PlayResourceLimits
from app.atlas.play.workspace_policy import (
    WorkspaceFileEntry,
    WorkspacePermission,
    decide_workspace_access,
)


ABSENT_REVISION = "absent"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_binary_file(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"\0" in handle.read(4096)


class PlayWorkspaceFileService:
    def __init__(self, *, project_root: str | Path, limits: PlayResourceLimits | None = None):
        self.project_root = Path(project_root).expanduser().resolve()
        self.limits = limits or PlayResourceLimits()

    def list_files(self, *, directory: str = ".", limit: int = 200) -> dict[str, Any]:
        limit = max(1, min(int(limit or 200), self.limits.max_related_files))
        decision = decide_workspace_access(
            project_root=self.project_root,
            relative_path=directory,
            permission=WorkspacePermission.READ,
            allow_root=True,
        )
        if not decision.allowed:
            return {"status": "blocked", "reason": decision.reason, "files": []}
        base = Path(decision.resolved_path)
        if not base.exists() or not base.is_dir():
            return {"status": "blocked", "reason": "directory_missing", "files": []}

        entries: list[WorkspaceFileEntry] = []
        for path in sorted(base.rglob("*")):
            if len(entries) >= limit:
                break
            if path.is_symlink():
                continue
            rel = path.relative_to(self.project_root).as_posix()
            read_decision = decide_workspace_access(
                project_root=self.project_root,
                relative_path=rel,
                permission=WorkspacePermission.READ,
            )
            if not read_decision.allowed:
                continue
            kind = "directory" if path.is_dir() else "file"
            size = path.stat().st_size if path.is_file() else 0
            digest = sha256_file(path) if path.is_file() and size <= self.limits.max_file_bytes else ""
            entries.append(
                WorkspaceFileEntry(
                    relative_path=rel,
                    kind=kind,
                    size_bytes=size,
                    sha256=digest,
                    writable=decide_workspace_access(
                        project_root=self.project_root,
                        relative_path=rel,
                        permission=WorkspacePermission.WRITE,
                    ).allowed,
                    executable=decide_workspace_access(
                        project_root=self.project_root,
                        relative_path=rel,
                        permission=WorkspacePermission.EXECUTE,
                    ).allowed,
                    servable=decide_workspace_access(
                        project_root=self.project_root,
                        relative_path=rel,
                        permission=WorkspacePermission.SERVE,
                    ).allowed,
                )
            )
        return {"status": "ok", "files": [entry.model_dump() for entry in entries], "truncated": len(entries) >= limit}

    def read_file(self, *, relative_path: str) -> dict[str, Any]:
        decision = decide_workspace_access(
            project_root=self.project_root,
            relative_path=relative_path,
            permission=WorkspacePermission.READ,
        )
        if not decision.allowed:
            return {"status": "blocked", "reason": decision.reason}
        path = Path(decision.resolved_path)
        if not path.exists() or not path.is_file():
            return {"status": "blocked", "reason": "file_missing"}
        size = path.stat().st_size
        if size > self.limits.max_file_bytes:
            return {"status": "blocked", "reason": "file_too_large"}
        if _is_binary_file(path):
            return {"status": "blocked", "reason": "binary_file"}
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"status": "blocked", "reason": "unsupported_encoding"}
        return {
            "status": "ok",
            "relative_path": decision.relative_path,
            "content": content,
            "sha256": sha256_file(path),
            "size_bytes": size,
        }

    def write_file(
        self,
        *,
        relative_path: str,
        content: str,
        expected_sha256: str,
    ) -> dict[str, Any]:
        if not expected_sha256:
            return {"status": "blocked", "reason": "revision_required"}
        encoded = str(content or "").encode("utf-8")
        if len(encoded) > self.limits.max_file_bytes:
            return {"status": "blocked", "reason": "content_too_large"}
        decision = decide_workspace_access(
            project_root=self.project_root,
            relative_path=relative_path,
            permission=WorkspacePermission.WRITE,
        )
        if not decision.allowed:
            return {"status": "blocked", "reason": decision.reason}
        path = Path(decision.resolved_path)
        existed = path.exists()
        if existed:
            if not path.is_file():
                return {"status": "blocked", "reason": "target_not_file"}
            if _is_binary_file(path):
                return {"status": "blocked", "reason": "binary_file"}
            current_sha = sha256_file(path)
            if expected_sha256 != current_sha:
                return {"status": "conflict", "reason": "stale_write_conflict", "current_sha256": current_sha}
        elif expected_sha256 != ABSENT_REVISION:
            return {"status": "conflict", "reason": "stale_write_conflict", "current_sha256": ABSENT_REVISION}

        parent_decision = decide_workspace_access(
            project_root=self.project_root,
            relative_path=path.parent.relative_to(self.project_root).as_posix()
            if path.parent != self.project_root
            else ".",
            permission=WorkspacePermission.WRITE,
            allow_root=True,
        )
        if not parent_decision.allowed:
            return {"status": "blocked", "reason": parent_decision.reason}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content or ""), encoding="utf-8")
        return {
            "status": "written",
            "relative_path": decision.relative_path,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "created": not existed,
        }
