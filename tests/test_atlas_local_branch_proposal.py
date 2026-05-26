from pathlib import Path

from app.atlas.local_branch_proposal import create_local_branch_proposal, read_local_branch_proposal
from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.patch_transaction_apply import apply_patch_transaction_one_action


def _approved_apply_kwargs() -> dict[str, object]:
    return {
        "dry_run_gate_ready": True,
        "rollback_ready": True,
        "confirmation_token_present": True,
        "confirmation_text": "EXECUTE ONE ACTION",
        "approval_status": "approved",
        "explicit_decision": "approve",
    }


def _create_applied_transaction(tmp_path: Path) -> tuple[Path, Path, dict[str, object], dict[str, object]]:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    (project / "a.txt").write_text("old\n", encoding="utf-8")
    txn = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_1",
        snapshot_manifest_path="/tmp/snap_manifest.json",
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
        diff_text="diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n",
        risk_class="low",
    )
    apply_result = apply_patch_transaction_one_action(
        manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
        **_approved_apply_kwargs(),
    )
    assert apply_result["status"] == "applied"
    return project, data_root, txn, apply_result


def test_create_local_branch_proposal_writes_proposal_only_manifest(tmp_path: Path) -> None:
    project, data_root, txn, apply_result = _create_applied_transaction(tmp_path)

    result = create_local_branch_proposal(
        manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
        apply_result_path=apply_result["apply_result_path"],
        base_ref="main",
        base_sha="abc123",
        approval_status="approved",
        explicit_decision="approve",
    )

    assert result["status"] == "created"
    assert result["proposal_only"] is True
    assert result["branch_creation_supported"] is False
    assert result["git_mutation_enabled"] is False
    assert result["draft_pr_creation_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    assert result["changed_files"] == ["a.txt"]
    manifest_path = Path(result["manifest_path"])
    assert manifest_path.exists()
    assert manifest_path.is_relative_to(data_root)
    manifest = read_local_branch_proposal(manifest_path=manifest_path, data_root=data_root)["manifest"]
    assert manifest["schema_version"] == "atlas.local_branch_proposal.v1"
    assert manifest["transaction_id"] == txn["transaction_id"]
    assert manifest["base_ref"] == "main"
    assert manifest["base_sha"] == "abc123"
    assert manifest["proposed_branch"].startswith("atlas/patch-")
    assert manifest["branch_creation_status"] == "not_created"
    assert manifest["manual_approval_required_for_branch_creation"] is True


def test_create_local_branch_proposal_blocks_without_approval_or_apply_result(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    (project / "a.txt").write_text("old\n", encoding="utf-8")
    txn = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_1",
        snapshot_manifest_path="/tmp/snap_manifest.json",
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
        diff_text="diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n",
        risk_class="low",
    )

    result = create_local_branch_proposal(manifest_path=txn["manifest_path"], data_root=data_root, project_path=project)

    assert result["status"] == "blocked"
    assert "explicit_human_approval_required" in result["blocked_reasons"]
    assert "apply_result_missing" in result["blocked_reasons"]
    assert result["branch_creation_supported"] is False
    assert result["git_mutation_enabled"] is False
    assert not Path(result["manifest_path"]).exists()


def test_create_local_branch_proposal_dry_run_does_not_write_manifest(tmp_path: Path) -> None:
    project, data_root, txn, apply_result = _create_applied_transaction(tmp_path)

    result = create_local_branch_proposal(
        manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
        apply_result_path=apply_result["apply_result_path"],
        approval_status="approved",
        explicit_decision="approve",
        dry_run=True,
    )

    assert result["status"] == "planned"
    assert result["proposal_only"] is True
    assert result["git_mutation_enabled"] is False
    assert not Path(result["manifest_path"]).exists()


def test_no_git_or_process_execution_in_local_branch_proposal_source() -> None:
    text = Path("app/atlas/local_branch_proposal.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert ".git" not in text
