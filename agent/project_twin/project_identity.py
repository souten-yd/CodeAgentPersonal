"""Project and workspace identity for the Digital Twin (PI-4).

Computes a stable logical ``project_id`` plus a separate ``workspace_id`` so that
simultaneous worktrees / sandboxes never share a twin (project isolation). Git is used
read-only when available; absence of git falls back to a path-based identity. No write,
no network, no Atlas workflow dependency.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from agent.project_intelligence.contracts import ProjectIdentity

# Files/dirs that do not constitute project source (mirrors project_mode ignore rules).
_IGNORE_NAMES = {
    ".git", ".gitignore", ".gitkeep", ".gitattributes",
    ".ds_store", "thumbs.db", ".atlas", "atlas_workspace", "ca_data",
    "__pycache__", ".pytest_cache", ".mypy_cache",
}


def _run_git(project_path: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(project_path), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    value = out.stdout.strip()
    return value or None


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _is_significant(rel_parts: tuple[str, ...]) -> bool:
    return not any(part.lower() in _IGNORE_NAMES for part in rel_parts)


def compute_working_tree_hash(project_path: Path, *, max_files: int = 5000, max_bytes_per_file: int = 1_000_000) -> str:
    """Deterministic hash of significant working-tree contents.

    The hash includes path, size, and bounded file content so same-size dirty edits still
    produce a distinct source identity. Large files are represented by size plus a head
    sample to keep identity computation bounded.
    """
    root = project_path.resolve()
    entries: list[str] = []
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if not _is_significant(rel.parts):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        try:
            with path.open("rb") as fh:
                sample = fh.read(max_bytes_per_file)
        except OSError:
            sample = b""
        content_hash = hashlib.sha256(sample).hexdigest()
        entries.append(f"{rel.as_posix()}\0{size}\0{content_hash}")
        count += 1
        if count >= max_files:
            break
    return _stable_hash("\n".join(entries))


def compute_project_identity(
    project_path: str | Path,
    *,
    workspace_id: str | None = None,
) -> ProjectIdentity:
    """Compute a stable logical project identity for ``project_path``.

    - ``project_id`` is stable for the same logical repository (git remote URL when
      present, otherwise the real repository/working-directory path);
    - ``workspace_id`` distinguishes worktrees/sandboxes: it derives from the git common
      dir + worktree toplevel (or the resolved path) so two worktrees of the same repo get
      different workspace ids and cannot leak into each other.
    """
    path = Path(project_path).resolve()

    remote = _run_git(path, "config", "--get", "remote.origin.url")
    toplevel = _run_git(path, "rev-parse", "--show-toplevel")
    branch = _run_git(path, "rev-parse", "--abbrev-ref", "HEAD")
    head = _run_git(path, "rev-parse", "HEAD")
    git_common = _run_git(path, "rev-parse", "--git-common-dir")

    logical = remote or toplevel or str(path)
    project_id = "proj_" + _stable_hash(logical)

    if workspace_id is None:
        # A worktree has a distinct toplevel even though it shares the common git dir;
        # include both so worktrees are isolated but a plain checkout is stable.
        worktree_seed = f"{git_common or ''}|{toplevel or path}"
        workspace_id = "ws_" + _stable_hash(worktree_seed)

    repository_identity = remote or toplevel
    return ProjectIdentity(
        project_id=project_id,
        workspace_id=workspace_id,
        project_path=str(path),
        repository_identity=repository_identity,
        branch_or_worktree=branch,
        source_revision=head,
        working_tree_hash=compute_working_tree_hash(path),
    )
