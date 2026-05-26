from pathlib import Path

import pytest

from app.atlas.candidate_workspace_manager import (
    STRATEGY_COPY_FALLBACK,
    STRATEGY_GIT_WORKTREE,
    create_candidate_workspace_plan,
    load_candidate_workspace_plan,
    validate_candidate_workspace_plan,
    write_candidate_workspace_plan,
)


def test_create_candidate_workspace_plan_ready_without_mutation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    candidate_root = tmp_path / "candidates"

    plan = create_candidate_workspace_plan(
        target_repo=repo,
        candidate_root=candidate_root,
        allowed_paths=["app/atlas", "tests"],
        blocked_paths=["main.py", "secrets", ".env"],
        stable_checkpoint_id="stable_001",
        max_files=5,
        max_risk_level="medium",
        self_improvement_scope="atlas_non_runtime",
        safety_profile_id="profile_001",
        recovery_manifest_path=tmp_path / "recovery" / "manifest.json",
    )

    assert plan["status"] == "ready"
    assert plan["candidate_workspace_manager_enabled"] is True
    assert plan["workspace_strategy"] == STRATEGY_GIT_WORKTREE
    assert plan["fallback_strategy"] == STRATEGY_COPY_FALLBACK
    assert plan["stable_checkpoint_required"] is True
    assert plan["recovery_manifest_required"] is True
    assert plan["safety_profile_required"] is True
    assert plan["allowed_paths"] == ["app/atlas", "tests"]
    assert plan["candidate_workspace_created"] is False
    assert plan["stable_runtime_mutation_enabled"] is False
    assert plan["command_execution_enabled"] is False
    assert plan["git_worktree_execution_enabled"] is False
    assert plan["copy_execution_enabled"] is False
    assert plan["patch_apply_enabled"] is False
    assert plan["verification_execution_enabled"] is False
    assert plan["promotion_enabled"] is False
    assert plan["direct_merge_enabled"] is False
    assert plan["remote_git_push_enabled"] is False
    assert plan["vue_authoritative"] is False


def test_candidate_workspace_plan_blocks_invalid_scope_and_paths(tmp_path: Path) -> None:
    plan = create_candidate_workspace_plan(
        target_repo=tmp_path / "repo",
        candidate_root=tmp_path / "repo" / "nested_candidate",
        allowed_paths=["*", "../outside"],
        blocked_paths=["app/atlas", "../outside"],
        stable_checkpoint_id="",
        max_files=0,
        max_risk_level="unknown",
        self_improvement_scope="none",
        workspace_strategy="shell",
        fallback_strategy="rsync",
    )

    assert plan["status"] == "blocked"
    assert plan["candidate_workspace_manager_enabled"] is False
    assert "stable_checkpoint_id_required" in plan["blocking_reasons"]
    assert "workspace_strategy_not_allowed" in plan["blocking_reasons"]
    assert "fallback_strategy_not_allowed" in plan["blocking_reasons"]
    assert "max_files_must_be_positive" in plan["blocking_reasons"]
    assert "max_risk_level_not_allowed" in plan["blocking_reasons"]
    assert "self_improvement_scope_not_allowed" in plan["blocking_reasons"]
    assert "allowed_path_too_broad" in plan["blocking_reasons"]
    assert "allowed_path_must_be_repo_relative" in plan["blocking_reasons"]
    assert "blocked_path_must_be_repo_relative" in plan["blocking_reasons"]
    assert "candidate_root_must_not_be_inside_target_repo" in plan["blocking_reasons"]


def test_validate_rejects_workspace_creation_enablement(tmp_path: Path) -> None:
    plan = create_candidate_workspace_plan(
        target_repo=tmp_path / "repo",
        candidate_root=tmp_path / "candidates",
        allowed_paths=["app/atlas"],
        blocked_paths=["main.py"],
        stable_checkpoint_id="stable_001",
        max_files=3,
        max_risk_level="low",
        self_improvement_scope="atlas_non_runtime",
    )
    plan["candidate_workspace_created"] = True

    with pytest.raises(ValueError, match="candidate_workspace_created"):
        validate_candidate_workspace_plan(plan)


def test_validate_rejects_stable_runtime_mutation(tmp_path: Path) -> None:
    plan = create_candidate_workspace_plan(
        target_repo=tmp_path / "repo",
        candidate_root=tmp_path / "candidates",
        allowed_paths=["docs"],
        blocked_paths=["app/runtime"],
        stable_checkpoint_id="stable_001",
        max_files=2,
        max_risk_level="low",
        self_improvement_scope="docs_tests_only",
    )
    plan["stable_runtime_mutation_enabled"] = True

    with pytest.raises(ValueError, match="stable_runtime_mutation_enabled"):
        validate_candidate_workspace_plan(plan)


def test_write_and_load_candidate_workspace_plan(tmp_path: Path) -> None:
    plan = create_candidate_workspace_plan(
        target_repo=tmp_path / "repo",
        candidate_root=tmp_path / "candidates",
        allowed_paths=["app/atlas"],
        blocked_paths=["main.py"],
        stable_checkpoint_id="stable_001",
        max_files=4,
        max_risk_level="medium",
        self_improvement_scope="atlas_non_runtime",
    )

    path = write_candidate_workspace_plan(plan=plan, destination=tmp_path / "data" / "candidate.json")
    loaded = load_candidate_workspace_plan(manifest_path=path)

    assert loaded["workspace_plan_id"] == plan["workspace_plan_id"]
    assert loaded["stable_checkpoint_id"] == "stable_001"


def test_candidate_workspace_manager_source_has_no_process_or_git_execution_dependency() -> None:
    text = Path("app/atlas/candidate_workspace_manager.py").read_text(encoding="utf-8")
    forbidden = [
        "subprocess",
        "os.system",
        "shutil.copy",
        "git worktree add",
        "requests",
        "FastAPI",
        "safe_apply",
    ]
    for needle in forbidden:
        assert needle not in text
