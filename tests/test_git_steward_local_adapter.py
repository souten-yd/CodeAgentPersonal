from __future__ import annotations

import subprocess
from pathlib import Path

from agent.git_steward.contracts import DEFAULT_EXCLUDE_PATTERNS
from agent.git_steward.local_adapter import (
    classify_external_publication,
    collect_diff,
    create_baseline_commit,
    create_local_commit,
    detect_repository,
    harden_ignore_policy,
    initialize_repository,
    prepare_branch,
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    initialize_repository(repo)
    _git(repo, "config", "user.email", "atlas@example.invalid")
    _git(repo, "config", "user.name", "Atlas Test")
    return repo


def test_repository_detection_and_init(tmp_path: Path) -> None:
    repo = tmp_path / "repo"

    before = detect_repository(repo)
    init = initialize_repository(repo)
    after = detect_repository(repo)

    assert before.exists is False
    assert init.status == "ok"
    assert after.exists is True
    assert after.git_dir


def test_ignore_policy_hardening_adds_sensitive_and_large_artifacts(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = harden_ignore_policy(repo)
    text = (repo / ".gitignore").read_text(encoding="utf-8")

    assert result.status == "ok"
    assert ".gitignore" in result.changed_files
    assert ".env" in text
    assert "*.gguf" in text
    assert set(DEFAULT_EXCLUDE_PATTERNS[:4]) <= set(text.splitlines())


def test_baseline_commit_then_branch_requires_clean_worktree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    harden_ignore_policy(repo)

    baseline = create_baseline_commit(repo)
    clean_branch = prepare_branch(repo, "codex/test-branch")
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    dirty_branch = prepare_branch(repo, "codex/blocked-branch")

    assert baseline.status == "ok"
    assert baseline.commit_sha
    assert clean_branch.status == "ok"
    assert clean_branch.branch == "codex/test-branch"
    assert dirty_branch.status == "blocked"
    assert "dirty_worktree" in dirty_branch.reasons
    assert "dirty.txt" in dirty_branch.changed_files


def test_baseline_commit_requires_ignore_policy_first(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")

    result = create_baseline_commit(repo)

    assert result.status == "blocked"
    assert "ignore_policy_missing" in result.reasons


def test_collect_diff_and_local_commit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    harden_ignore_policy(repo)
    create_baseline_commit(repo)
    (repo / "README.md").write_text("baseline\nchanged\n", encoding="utf-8")

    diff = collect_diff(repo)
    commit = create_local_commit(repo, message="Update readme")
    state = detect_repository(repo)

    assert diff.status == "ok"
    assert diff.changed_files == ["README.md"]
    assert commit.status == "ok"
    assert commit.commit_sha
    assert state.dirty is False


def test_external_publication_returns_approval_needed_without_running_remote() -> None:
    result = classify_external_publication("push")

    assert result.status == "approval_needed"
    assert result.approval_required is True
    assert "remote_publication" in result.reasons
