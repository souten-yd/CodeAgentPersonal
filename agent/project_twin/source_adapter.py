"""Workspace-safe project source snapshots for the concrete Digital Twin (PIR-3)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from agent.project_intelligence.contracts import IntelligenceDiagnostic, IntelligenceErrorCode, ProjectIdentity
from agent.project_twin.behavioral_graph import ANALYZER_VERSION
from agent.project_twin.project_identity import compute_project_identity
from agent.project_twin.static_graph import PARSER_VERSION

SOURCE_ADAPTER_VERSION = "source_adapter.pir3"

_IGNORE_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "dist",
    "build",
    "ca_data",
    "atlas_workspace",
    # .claude/worktrees holds full COPIES of the repo — indexing them duplicates every symbol/test and
    # over-connects impact. Exclude agent state, virtualenvs, and IDE/coverage dirs.
    ".claude",
    "venv_sys",
    ".venv",
    "venv",
    "tts_envs",
    "third_party",
    ".idea",
    ".vscode",
    "htmlcov",
    ".tox",
}
_TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".vue",
    ".html",
    ".css",
    ".json",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
}


@dataclass(frozen=True)
class SourceFileSnapshot:
    path: str
    size: int
    content_hash: str


@dataclass(frozen=True)
class SourceSnapshot:
    project: ProjectIdentity
    root: Path
    files: list[SourceFileSnapshot]
    changed_paths: list[str]
    deleted_paths: list[str]
    parser_manifest: dict[str, str] = field(default_factory=dict)
    diagnostics: list[IntelligenceDiagnostic] = field(default_factory=list)


class SourceSnapshotError(Exception):
    """Raised when a source snapshot would violate project/workspace safety."""


def _diagnostic(code: IntelligenceErrorCode, message: str, *, severity: str = "warning") -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, severity=severity)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _run_git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def _ignored(rel: Path) -> bool:
    return any(part.lower() in _IGNORE_NAMES for part in rel.parts)


def _is_text_candidate(path: Path) -> bool:
    if path.suffix.lower() in _TEXT_SUFFIXES:
        return True
    try:
        return b"\0" not in path.read_bytes()[:2048]
    except OSError:
        return False


def _hash_file(path: Path, *, max_bytes: int) -> str:
    import hashlib

    digest = hashlib.sha256()
    remaining = max_bytes
    with path.open("rb") as fh:
        while remaining > 0:
            chunk = fh.read(min(65536, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


class ProjectSourceAdapter:
    """Read-only adapter that turns a workspace path into a bounded source snapshot."""

    def __init__(self, *, max_files: int = 5000, max_file_bytes: int = 1_000_000) -> None:
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes

    def snapshot(
        self,
        project_path: str | Path,
        *,
        workspace_id: str | None = None,
        requested_changed_paths: list[str] | None = None,
    ) -> SourceSnapshot:
        root = Path(project_path).expanduser().resolve()
        if not root.is_dir():
            raise SourceSnapshotError(f"project path is not a directory: {project_path}")

        identity = compute_project_identity(root, workspace_id=workspace_id)
        files: list[SourceFileSnapshot] = []
        diagnostics: list[IntelligenceDiagnostic] = []

        for path in sorted(root.rglob("*")):
            if len(files) >= self.max_files:
                diagnostics.append(_diagnostic(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE, "source file count limit reached"))
                break
            if not path.is_file():
                continue
            try:
                resolved = path.resolve()
                rel = resolved.relative_to(root)
            except (OSError, ValueError):
                diagnostics.append(_diagnostic(IntelligenceErrorCode.UNSAFE_OPERATION_REQUIRED, f"skipped unsafe path: {path}"))
                continue
            if not _is_under(resolved, root) or _ignored(rel):
                continue
            if path.is_symlink() and not _is_under(resolved, root):
                diagnostics.append(_diagnostic(IntelligenceErrorCode.UNSAFE_OPERATION_REQUIRED, f"skipped symlink escape: {rel.as_posix()}"))
                continue
            try:
                size = resolved.stat().st_size
            except OSError:
                continue
            if size > self.max_file_bytes:
                diagnostics.append(_diagnostic(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE, f"skipped oversized source file: {rel.as_posix()}"))
                continue
            if not _is_text_candidate(resolved):
                diagnostics.append(_diagnostic(IntelligenceErrorCode.ANALYSIS_UNAVAILABLE, f"skipped binary source file: {rel.as_posix()}"))
                continue
            files.append(SourceFileSnapshot(path=rel.as_posix(), size=size, content_hash=_hash_file(resolved, max_bytes=self.max_file_bytes)))

        changed, deleted = self._changed_paths(root, requested_changed_paths=requested_changed_paths)
        known = {f.path for f in files}
        deleted = sorted(set(deleted) | {p for p in changed if p not in known and not (root / p).exists()})
        changed = sorted(set(changed) | set(deleted))
        return SourceSnapshot(
            project=identity,
            root=root,
            files=files,
            changed_paths=changed,
            deleted_paths=deleted,
            parser_manifest={
                "source_adapter": SOURCE_ADAPTER_VERSION,
                "static_graph": PARSER_VERSION,
                "behavioral_graph": ANALYZER_VERSION,
            },
            diagnostics=diagnostics,
        )

    def _changed_paths(self, root: Path, *, requested_changed_paths: list[str] | None) -> tuple[list[str], list[str]]:
        if requested_changed_paths:
            changed = [self._safe_rel(root, path) for path in requested_changed_paths]
            return sorted({p for p in changed if p}), []

        status = _run_git(root, "status", "--porcelain=v1", "--untracked-files=all")
        if status is None:
            return [], []

        changed: set[str] = set()
        deleted: set[str] = set()
        for line in status.splitlines():
            if not line:
                continue
            code = line[:2]
            raw = line[3:]
            if " -> " in raw:
                _, raw = raw.split(" -> ", 1)
            rel = self._safe_rel(root, raw.strip('"'))
            if not rel:
                continue
            changed.add(rel)
            if "D" in code:
                deleted.add(rel)
        return sorted(changed), sorted(deleted)

    def _safe_rel(self, root: Path, value: str) -> str:
        candidate = (root / value).resolve()
        if not _is_under(candidate, root):
            raise SourceSnapshotError(f"path escapes project root: {value}")
        return candidate.relative_to(root).as_posix()
