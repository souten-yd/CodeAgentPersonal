import json
from pathlib import Path

import pytest

from app.atlas.candidate_workspace_manager import create_candidate_workspace_plan, write_candidate_workspace_plan
from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.self_improvement_candidate_apply import (
    REQUIRED_CONFIRMATION_TEXT,
    apply_self_improvement_candidate_patch_one_action,
    validate_self_improvement_candidate_apply,
)


def _write_dry_run_verification(data_root: Path) -> Path:
    verification_dir = data_root / "atlas" / "self_improvement_dry_run_verifications" / "verify_1"
    verification_dir.mkdir(parents=True)
    manifest: dict[str, object] = {
        "schema_version": "atlas.self_improvement_dry_run_verification.v1",
        "verification_id": "verify_1",
        "track_pr": "PR-ATLAS-SCALE-143",
        "next_required_pr": "PR-ATLAS-SCALE-144",
        "dry_run_verification_authorized": True,
        "self_improvement_dry_run_verification_enabled": True,
        "strict_gate_required": True,
        "allowed_commands": ["pytest -q tests/test_atlas_self_improvement_candidate_apply.py"],
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_applied": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    path = verification_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def _candidate_plan(tmp_path: Path, *, allowed_paths: list[str] | None = None, max_risk_level: str = "strict") -> Path:
    plan = create_candidate_workspace_plan(
        target_repo=tmp_path / "stable_repo",
        candidate_root=tmp_path / "candidate_repo",
        allowed_paths=allowed_paths or ["app/atlas"],
        blocked_paths=["main.py", ".env", "secrets"],
        stable_checkpoint_id="stable_001",
        max_files=2,
        max_risk_level=max_risk_level,
        self_improvement_scope="atlas_non_runtime",
        safety_profile_id="profile_001",
        recovery_manifest_path=tmp_path / "recovery" / "manifest.json",
    )
    return write_candidate_workspace_plan(plan=plan, destination=tmp_path / "candidate_plan.json")


def _transaction(candidate_root: Path, data_root: Path, *, relative_path: str = "app/atlas/a.txt") -> Path:
    target = candidate_root / relative_path
    target.parent.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    diff = (
        f"diff --git a/{relative_path} b/{relative_path}\n"
        f"--- a/{relative_path}\n"
        f"+++ b/{relative_path}\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    created = create_patch_transaction(
        project_path=candidate_root,
        data_root=data_root,
        snapshot_id="snap_1",
        snapshot_manifest_path=str(data_root / "snapshots" / "snap_1.json"),
        proposed_files=[{"relative_path": relative_path, "change_type": "modify"}],
        diff_text=diff,
        risk_class="strict_gate",
    )
    path = Path(str(created["manifest_path"]))
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["proposed_files"] = [
        {
            "relative_path": relative_path,
            "change_type": "modify",
            "path_valid": True,
            "exists_before": True,
            "warnings": [],
        }
    ]
    manifest["file_count"] = 1
    manifest["changed_file_count"] = 1
    manifest["diff_summary"]["total_files"] = 1
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def _approved_kwargs() -> dict[str, object]:
    return {
        "dry_run_gate_ready": True,
        "rollback_ready": True,
        "strict_gate_approved": True,
        "confirmation_token_present": True,
        "confirmation_text": REQUIRED_CONFIRMATION_TEXT,
        "approval_status": "approved",
        "explicit_decision": "approve",
    }


def test_candidate_apply_applies_only_inside_candidate_workspace(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    candidate_root = tmp_path / "candidate_repo"
    stable_root = tmp_path / "stable_repo"
    stable_root.mkdir()
    plan = _candidate_plan(tmp_path)
    verification = _write_dry_run_verification(data_root)
    transaction = _transaction(candidate_root, data_root)

    result = apply_self_improvement_candidate_patch_one_action(
        candidate_workspace_plan_path=plan,
        dry_run_verification_path=verification,
        patch_transaction_manifest_path=transaction,
        data_root=data_root,
        **_approved_kwargs(),
    )

    assert result["status"] == "applied"
    assert result["changed_files"] == ["app/atlas/a.txt"]
    assert (candidate_root / "app/atlas/a.txt").read_text(encoding="utf-8") == "new\n"
    assert not (stable_root / "app/atlas/a.txt").exists()
    assert result["candidate_apply_enabled"] is True
    assert result["candidate_apply_performed"] is True
    assert result["candidate_workspace_mutation_performed"] is True
    assert result["stable_runtime_mutation_enabled"] is False
    assert result["stable_runtime_mutation_performed"] is False
    assert result["self_apply_enabled"] is False
    assert result["self_modification_enabled"] is False
    assert result["direct_merge_enabled"] is False
    assert result["remote_git_push_enabled"] is False
    assert result["command_execution_enabled"] is False


def test_candidate_apply_dry_run_plans_without_mutation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    candidate_root = tmp_path / "candidate_repo"
    plan = _candidate_plan(tmp_path)
    verification = _write_dry_run_verification(data_root)
    transaction = _transaction(candidate_root, data_root)

    result = apply_self_improvement_candidate_patch_one_action(
        candidate_workspace_plan_path=plan,
        dry_run_verification_path=verification,
        patch_transaction_manifest_path=transaction,
        data_root=data_root,
        dry_run=True,
        **_approved_kwargs(),
    )

    assert result["status"] == "planned"
    assert result["changed_files"] == ["app/atlas/a.txt"]
    assert (candidate_root / "app/atlas/a.txt").read_text(encoding="utf-8") == "old\n"
    assert result["candidate_apply_enabled"] is True
    assert result["candidate_apply_performed"] is False
    assert result["candidate_workspace_mutation_performed"] is False


def test_candidate_apply_blocks_outside_allowed_paths(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    candidate_root = tmp_path / "candidate_repo"
    plan = _candidate_plan(tmp_path, allowed_paths=["docs"])
    verification = _write_dry_run_verification(data_root)
    transaction = _transaction(candidate_root, data_root, relative_path="app/atlas/a.txt")

    result = apply_self_improvement_candidate_patch_one_action(
        candidate_workspace_plan_path=plan,
        dry_run_verification_path=verification,
        patch_transaction_manifest_path=transaction,
        data_root=data_root,
        **_approved_kwargs(),
    )

    assert result["status"] == "blocked"
    assert "changed_file_outside_candidate_allowed_paths" in result["blocking_reasons"]
    assert (candidate_root / "app/atlas/a.txt").read_text(encoding="utf-8") == "old\n"
    assert result["candidate_apply_enabled"] is False
    assert result["candidate_apply_performed"] is False


def test_candidate_apply_requires_candidate_confirmation_text(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    candidate_root = tmp_path / "candidate_repo"
    plan = _candidate_plan(tmp_path)
    verification = _write_dry_run_verification(data_root)
    transaction = _transaction(candidate_root, data_root)
    kwargs = _approved_kwargs()
    kwargs["confirmation_text"] = "APPLY SELF IMPROVEMENT PATCH"

    result = apply_self_improvement_candidate_patch_one_action(
        candidate_workspace_plan_path=plan,
        dry_run_verification_path=verification,
        patch_transaction_manifest_path=transaction,
        data_root=data_root,
        **kwargs,
    )

    assert result["status"] == "blocked"
    assert "candidate_confirmation_text_mismatch" in result["blocking_reasons"]
    assert result["candidate_apply_performed"] is False


def test_validate_rejects_stable_mutation_flag(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    candidate_root = tmp_path / "candidate_repo"
    plan = _candidate_plan(tmp_path)
    verification = _write_dry_run_verification(data_root)
    transaction = _transaction(candidate_root, data_root)
    result = apply_self_improvement_candidate_patch_one_action(
        candidate_workspace_plan_path=plan,
        dry_run_verification_path=verification,
        patch_transaction_manifest_path=transaction,
        data_root=data_root,
        dry_run=True,
        **_approved_kwargs(),
    )
    result["stable_runtime_mutation_enabled"] = True

    with pytest.raises(ValueError, match="stable_runtime_mutation_enabled"):
        validate_self_improvement_candidate_apply(result)


def test_candidate_apply_source_has_no_process_or_remote_git_dependency() -> None:
    text = Path("app/atlas/self_improvement_candidate_apply.py").read_text(encoding="utf-8")
    forbidden = [
        "subprocess",
        "os.system",
        "requests",
        "from fastapi",
        "import fastapi",
        "uvicorn",
        "git push",
        "git worktree",
        "self_apply_to_stable_runtime",
    ]
    for needle in forbidden:
        assert needle not in text
