from pathlib import Path

from app.atlas.draft_pr_policy import create_draft_pr_policy_metadata, read_draft_pr_policy_metadata
from app.atlas.local_branch_proposal import create_approved_local_branch, create_local_branch_proposal, read_local_branch_proposal
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


def _approved_branch_kwargs() -> dict[str, object]:
    return {
        "approval_status": "approved",
        "explicit_decision": "approve",
        "confirmation_token_present": True,
        "confirmation_text": "CREATE LOCAL BRANCH",
    }


def _create_created_branch(tmp_path: Path) -> tuple[Path, Path, dict[str, object], dict[str, object]]:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    (project / ".git" / "refs" / "heads").mkdir(parents=True)
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
    proposal = create_local_branch_proposal(
        manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
        apply_result_path=apply_result["apply_result_path"],
        base_ref="main",
        base_sha="a" * 40,
        approval_status="approved",
        explicit_decision="approve",
    )
    assert proposal["status"] == "created"
    branch = create_approved_local_branch(
        proposal_manifest_path=proposal["manifest_path"],
        data_root=data_root,
        project_path=project,
        **_approved_branch_kwargs(),
    )
    assert branch["status"] == "created"
    return project, data_root, proposal, branch


def test_create_draft_pr_policy_metadata_writes_policy_only_manifest(tmp_path: Path) -> None:
    _project, data_root, proposal, branch = _create_created_branch(tmp_path)

    result = create_draft_pr_policy_metadata(
        proposal_manifest_path=proposal["manifest_path"],
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
    )

    assert result["status"] == "created"
    assert result["head_branch"] == branch["branch_name"]
    assert result["base_ref"] == "main"
    assert result["policy_only"] is True
    assert result["draft_pr_creation_enabled"] is False
    assert result["push_enabled"] is False
    assert result["pr_update_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    manifest_path = Path(result["manifest_path"])
    assert manifest_path.exists()
    manifest = read_draft_pr_policy_metadata(manifest_path=manifest_path, data_root=data_root)["manifest"]
    assert manifest["schema_version"] == "atlas.draft_pr_policy.v1"
    assert manifest["draft_pr_creation_enabled"] is False
    assert manifest["push_enabled"] is False
    assert manifest["pr_update_enabled"] is False
    assert manifest["manual_approval_required_for_draft_pr_creation"] is True
    proposal_manifest = read_local_branch_proposal(manifest_path=proposal["manifest_path"], data_root=data_root)["manifest"]
    assert proposal_manifest["draft_pr_policy_status"] == "created"


def test_create_draft_pr_policy_metadata_blocks_without_approval(tmp_path: Path) -> None:
    _project, data_root, proposal, _branch = _create_created_branch(tmp_path)

    result = create_draft_pr_policy_metadata(proposal_manifest_path=proposal["manifest_path"], data_root=data_root)

    assert result["status"] == "blocked"
    assert "explicit_human_approval_required" in result["blocked_reasons"]
    assert result["draft_pr_creation_enabled"] is False
    assert not Path(result["manifest_path"]).exists()


def test_create_draft_pr_policy_metadata_blocks_before_branch_creation(tmp_path: Path) -> None:
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
    proposal = create_local_branch_proposal(
        manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
        apply_result_path=apply_result["apply_result_path"],
        base_ref="main",
        base_sha="a" * 40,
        approval_status="approved",
        explicit_decision="approve",
    )

    result = create_draft_pr_policy_metadata(
        proposal_manifest_path=proposal["manifest_path"],
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
    )

    assert result["status"] == "blocked"
    assert "branch_creation_required" in result["blocked_reasons"]
    assert "branch_creation_result_required" in result["blocked_reasons"]


def test_create_draft_pr_policy_metadata_dry_run_does_not_write_manifest(tmp_path: Path) -> None:
    _project, data_root, proposal, _branch = _create_created_branch(tmp_path)

    result = create_draft_pr_policy_metadata(
        proposal_manifest_path=proposal["manifest_path"],
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        dry_run=True,
    )

    assert result["status"] == "planned"
    assert result["policy_only"] is True
    assert result["draft_pr_creation_enabled"] is False
    assert not Path(result["manifest_path"]).exists()


def test_no_network_or_process_execution_in_draft_pr_policy_source() -> None:
    text = Path("app/atlas/draft_pr_policy.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
