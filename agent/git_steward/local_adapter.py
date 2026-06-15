"""Concrete local Git adapter for Atlas Git Steward.

Only local repository operations are executed. Remote publication/admin
operations return approval-needed results and are never run here.
"""
from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
from typing import Iterable

from agent.git_steward.contracts import (
    DEFAULT_EXCLUDE_PATTERNS,
    GitRepositoryState,
    GitStewardResult,
    classify_git_operation,
    normalize_repo_path,
)

# Files that must never be committed by default: secrets, credentials, model weights,
# databases, and runtime/generated data. A superset-by-intent of DEFAULT_EXCLUDE_PATTERNS.
FORBIDDEN_COMMIT_PATTERNS: tuple[str, ...] = (
    ".env", ".env.*", "*.key", "*.pem", "credentials.*", "secrets.*", "*.secret",
    "id_rsa", "id_ed25519", "*.sqlite3", "*.db", "*.gguf", "*.safetensors", "*.pt",
    "*.onnx", "*.bin", "*.pyc",
)
# Directory prefixes (runtime/generated data and caches) that must not be committed.
FORBIDDEN_COMMIT_DIRS: tuple[str, ...] = ("ca_data/", "logs/", "__pycache__/", ".venv/", "venv/", "node_modules/")


def _run_git(repo: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=check,
        text=True,
        capture_output=True,
    )


def _status_lines(repo: Path) -> list[str]:
    result = _run_git(repo, ["status", "--porcelain"], check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def detect_repository(path: str | Path) -> GitRepositoryState:
    repo = normalize_repo_path(path)
    exists = repo.exists()
    if not exists:
        return GitRepositoryState(path=str(repo), exists=False)
    git_dir = _run_git(repo, ["rev-parse", "--git-dir"], check=False)
    if git_dir.returncode != 0:
        return GitRepositoryState(path=str(repo), exists=True)
    branch = _run_git(repo, ["branch", "--show-current"], check=False).stdout.strip()
    head = _run_git(repo, ["rev-parse", "--verify", "HEAD"], check=False)
    head_sha = head.stdout.strip() if head.returncode == 0 else ""
    untracked: list[str] = []
    changed: list[str] = []
    for line in _status_lines(repo):
        path_part = line[3:] if len(line) > 3 else ""
        if line.startswith("?? "):
            untracked.append(path_part)
        else:
            changed.append(path_part)
    return GitRepositoryState(
        path=str(repo),
        exists=True,
        git_dir=git_dir.stdout.strip(),
        branch=branch,
        head_sha=head_sha,
        dirty=bool(untracked or changed),
        untracked_files=sorted(untracked),
        changed_files=sorted(changed),
    )


def initialize_repository(path: str | Path) -> GitStewardResult:
    repo = normalize_repo_path(path)
    repo.mkdir(parents=True, exist_ok=True)
    state = detect_repository(repo)
    if state.git_dir:
        return GitStewardResult(operation="init", status="ok", reasons=["repository_exists"])
    _run_git(repo, ["init"])
    return GitStewardResult(operation="init", status="ok", reasons=["repository_initialized"])


def harden_ignore_policy(path: str | Path, *, patterns: Iterable[str] = DEFAULT_EXCLUDE_PATTERNS) -> GitStewardResult:
    repo = normalize_repo_path(path)
    ignore_path = repo / ".gitignore"
    existing = ignore_path.read_text(encoding="utf-8").splitlines() if ignore_path.exists() else []
    merged = list(existing)
    added: list[str] = []
    for pattern in patterns:
        if pattern not in merged:
            merged.append(pattern)
            added.append(pattern)
    ignore_path.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")
    return GitStewardResult(operation="ignore-policy", status="ok", changed_files=[".gitignore"], reasons=[f"patterns_added={len(added)}"])


def create_baseline_commit(path: str | Path, *, message: str = "Atlas baseline") -> GitStewardResult:
    repo = normalize_repo_path(path)
    state = detect_repository(repo)
    if not state.git_dir:
        return GitStewardResult(operation="baseline-commit", status="blocked", reasons=["repository_not_initialized"])
    if not (repo / ".gitignore").exists():
        return GitStewardResult(operation="baseline-commit", status="blocked", reasons=["ignore_policy_missing"])
    _run_git(repo, ["add", "."])
    status = _status_lines(repo)
    if not status:
        return GitStewardResult(operation="baseline-commit", status="ok", commit_sha=state.head_sha, reasons=["nothing_to_commit"])
    _run_git(repo, ["commit", "-m", message])
    head = _run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
    return GitStewardResult(operation="baseline-commit", status="ok", commit_sha=head, reasons=["baseline_committed"])


def prepare_branch(path: str | Path, branch_name: str, *, require_clean: bool = True) -> GitStewardResult:
    repo = normalize_repo_path(path)
    state = detect_repository(repo)
    if not state.git_dir:
        return GitStewardResult(operation="prepare-branch", status="blocked", branch=branch_name, reasons=["repository_not_initialized"])
    if require_clean and state.dirty:
        return GitStewardResult(
            operation="prepare-branch",
            status="blocked",
            branch=branch_name,
            changed_files=[*state.changed_files, *state.untracked_files],
            reasons=["dirty_worktree"],
        )
    _run_git(repo, ["checkout", "-B", branch_name])
    head = _run_git(repo, ["rev-parse", "HEAD"], check=False).stdout.strip()
    return GitStewardResult(operation="prepare-branch", status="ok", branch=branch_name, commit_sha=head, reasons=["branch_prepared"])


def collect_diff(path: str | Path) -> GitStewardResult:
    repo = normalize_repo_path(path)
    state = detect_repository(repo)
    if not state.git_dir:
        return GitStewardResult(operation="diff", status="blocked", reasons=["repository_not_initialized"])
    result = _run_git(repo, ["diff", "--name-only"], check=False)
    changed = sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    return GitStewardResult(operation="diff", status="ok", diff_ref="working_tree", changed_files=changed, reasons=["diff_collected"])


def create_local_commit(path: str | Path, *, message: str, paths: Iterable[str] = ()) -> GitStewardResult:
    repo = normalize_repo_path(path)
    state = detect_repository(repo)
    if not state.git_dir:
        return GitStewardResult(operation="commit", status="blocked", reasons=["repository_not_initialized"])
    path_list = [p for p in paths if str(p).strip()]
    _run_git(repo, ["add", *path_list] if path_list else ["add", "."])
    if not _status_lines(repo):
        return GitStewardResult(operation="commit", status="ok", commit_sha=state.head_sha, reasons=["nothing_to_commit"])
    _run_git(repo, ["commit", "-m", message])
    head = _run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
    return GitStewardResult(operation="commit", status="ok", commit_sha=head, reasons=["local_commit_created"])


def is_within_workspace(repo_path: str | Path, allowed_roots: Iterable[str | Path]) -> bool:
    """True when ``repo_path`` resolves inside one of the Atlas-owned/approved roots."""
    repo = normalize_repo_path(repo_path)
    for root in allowed_roots or ():
        root_p = normalize_repo_path(root)
        try:
            repo.relative_to(root_p)
            return True
        except ValueError:
            continue
    return False


def _is_forbidden_path(path: str) -> bool:
    norm = path.replace("\\", "/").strip()
    if not norm:
        return False
    name = norm.rsplit("/", 1)[-1]
    for seg in FORBIDDEN_COMMIT_DIRS:
        if norm.startswith(seg) or f"/{seg}" in f"/{norm}":
            return True
    for pat in FORBIDDEN_COMMIT_PATTERNS:
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(norm, pat):
            return True
    return False


def forbidden_committed_files(path: str | Path, *, paths: Iterable[str] = ()) -> list[str]:
    """Return worktree files that would be committed but match a forbidden pattern
    (secrets, keys, model weights, DB files, runtime/generated data)."""
    repo = normalize_repo_path(path)
    candidates: list[str]
    explicit = [str(p).strip() for p in paths if str(p).strip()]
    if explicit:
        candidates = explicit
    else:
        candidates = []
        for line in _status_lines(repo):
            part = line[3:] if len(line) > 3 else ""
            if part:
                candidates.append(part)
    return sorted({c for c in candidates if _is_forbidden_path(c)})


def safe_local_commit(
    path: str | Path,
    *,
    message: str,
    paths: Iterable[str] = (),
    allowed_roots: Iterable[str | Path] | None = None,
    require_ignore_policy: bool = True,
) -> GitStewardResult:
    """Local commit with workspace-scope, ignore-policy, and secret/large-artifact guards.

    Blocks (without committing) when: the repo is outside the approved workspace roots,
    the ignore policy is missing, or any file to be committed matches a forbidden pattern.
    Remote operations are never performed here."""
    repo = normalize_repo_path(path)
    if allowed_roots is not None and not is_within_workspace(repo, allowed_roots):
        return GitStewardResult(operation="commit", status="blocked", reasons=["outside_atlas_workspace"])
    state = detect_repository(repo)
    if not state.git_dir:
        return GitStewardResult(operation="commit", status="blocked", reasons=["repository_not_initialized"])
    if require_ignore_policy and not (repo / ".gitignore").exists():
        return GitStewardResult(operation="commit", status="blocked", reasons=["ignore_policy_missing"])
    forbidden = forbidden_committed_files(repo, paths=paths)
    if forbidden:
        return GitStewardResult(operation="commit", status="blocked",
                                changed_files=forbidden,
                                reasons=["forbidden_files_blocked", *(f"forbidden:{f}" for f in forbidden)])
    return create_local_commit(repo, message=message, paths=paths)


def git_evidence_refs(result: GitStewardResult) -> list[str]:
    """Project a Git Steward result into Proof Ledger evidence refs."""
    refs: list[str] = [f"git:{result.operation}:{result.status}"]
    if result.commit_sha:
        refs.append(f"git_commit:{result.commit_sha}")
    if result.branch:
        refs.append(f"git_branch:{result.branch}")
    for changed in result.changed_files:
        refs.append(f"git_changed:{changed}")
    return refs


def classify_external_publication(operation: str = "push") -> GitStewardResult:
    decision = classify_git_operation(operation)
    return GitStewardResult(
        operation=operation,
        status="approval_needed" if decision.approval_required else "ok",
        approval_required=decision.approval_required,
        reasons=decision.reasons,
    )


__all__ = [
    "FORBIDDEN_COMMIT_PATTERNS",
    "FORBIDDEN_COMMIT_DIRS",
    "classify_external_publication",
    "collect_diff",
    "create_baseline_commit",
    "create_local_commit",
    "detect_repository",
    "forbidden_committed_files",
    "git_evidence_refs",
    "harden_ignore_policy",
    "initialize_repository",
    "is_within_workspace",
    "prepare_branch",
    "safe_local_commit",
]
