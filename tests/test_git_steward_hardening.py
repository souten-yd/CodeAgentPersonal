"""Step 8 — Git Steward hardening: workspace scope, secret/artifact guard, evidence."""
from __future__ import annotations

from agent.git_steward.local_adapter import (
    classify_external_publication,
    create_local_commit,
    forbidden_committed_files,
    git_evidence_refs,
    harden_ignore_policy,
    initialize_repository,
    is_within_workspace,
    safe_local_commit,
)


def _repo(path):
    initialize_repository(path)
    harden_ignore_policy(path)
    return path


def test_commit_outside_workspace_is_blocked(tmp_path):
    repo = _repo(tmp_path / "outside")
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    res = safe_local_commit(repo, message="m", allowed_roots=[tmp_path / "allowed"])
    assert res.status == "blocked"
    assert "outside_atlas_workspace" in res.reasons


def test_commit_inside_workspace_succeeds(tmp_path):
    root = tmp_path / "ws"
    repo = _repo(root / "proj")
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    res = safe_local_commit(repo, message="m", allowed_roots=[root])
    assert res.status == "ok"
    assert res.commit_sha


def test_secrets_and_artifacts_are_not_committed(tmp_path):
    repo = _repo(tmp_path / "proj")
    # Even if a caller explicitly stages forbidden paths, the guard refuses them.
    staged = [".env", "model.gguf", "data.sqlite3", "ok.py"]
    for f in staged:
        (repo / f).write_text("x\n", encoding="utf-8")
    forbidden = forbidden_committed_files(repo, paths=staged)
    assert ".env" in forbidden and "model.gguf" in forbidden and "data.sqlite3" in forbidden
    assert "ok.py" not in forbidden
    res = safe_local_commit(repo, message="m", paths=staged)
    assert res.status == "blocked"
    assert "forbidden_files_blocked" in res.reasons


def test_unignored_forbidden_file_caught_by_status(tmp_path):
    # A forbidden file NOT covered by the ignore policy is still caught via worktree status.
    repo = tmp_path / "proj"
    initialize_repository(repo)
    (repo / ".gitignore").write_text("# minimal, does not ignore secrets\n", encoding="utf-8")
    (repo / "id_rsa").write_text("PRIVATE KEY\n", encoding="utf-8")
    assert "id_rsa" in forbidden_committed_files(repo)


def test_ignore_policy_required(tmp_path):
    repo = tmp_path / "proj"
    initialize_repository(repo)  # no harden_ignore_policy
    (repo / "a.py").write_text("x=1\n", encoding="utf-8")
    res = safe_local_commit(repo, message="m")
    assert res.status == "blocked"
    assert "ignore_policy_missing" in res.reasons


def test_remote_publication_remains_approval_bound():
    for op in ("push", "create-pr", "merge-pr", "force-push"):
        res = classify_external_publication(op)
        assert res.approval_required is True
        assert res.status == "approval_needed"


def test_is_within_workspace(tmp_path):
    root = tmp_path / "ws"
    (root / "proj").mkdir(parents=True)
    assert is_within_workspace(root / "proj", [root]) is True
    assert is_within_workspace(tmp_path / "other", [root]) is False


def test_local_commit_evidence_available_to_proof_ledger(tmp_path):
    repo = _repo(tmp_path / "proj")
    (repo / "a.py").write_text("x=1\n", encoding="utf-8")
    res = create_local_commit(repo, message="m")
    refs = git_evidence_refs(res)
    assert any(r.startswith("git:commit:") for r in refs)
    assert any(r.startswith("git_commit:") for r in refs)
