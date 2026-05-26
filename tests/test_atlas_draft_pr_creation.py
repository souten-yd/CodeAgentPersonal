from pathlib import Path

from app.atlas.draft_pr_creation import create_manually_approved_draft_pr, read_draft_pr_creation_result
from app.atlas.draft_pr_policy import create_draft_pr_policy_metadata
from app.atlas.local_branch_proposal import create_approved_local_branch, create_local_branch_proposal, read_local_branch_proposal
from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.patch_transaction_apply import apply_patch_transaction_one_action


class FakeDraftPrClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_draft_pull_request(self, *, base_ref: str, head_branch: str, title: str, body: str) -> dict[str, object]:
        self.calls.append({"base_ref": base_ref, "head_branch": head_branch, "title": title, "body": body})
        return {"number": 134, "html_url": "https://example.test/pr/134", "url": "https://api.example.test/pr/134", "draft": True}


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


def _create_policy(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, object]]:
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
    branch = create_approved_local_branch(
        proposal_manifest_path=proposal["manifest_path"],
        data_root=data_root,
        project_path=project,
        **_approved_branch_kwargs(),
    )
    policy = create_draft_pr_policy_metadata(
        proposal_manifest_path=proposal["manifest_path"],
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
    )
    assert policy["status"] == "created"
    return data_root, policy, branch


def test_create_manually_approved_draft_pr_writes_result_with_injected_client(tmp_path: Path) -> None:
    data_root, policy, branch = _create_policy(tmp_path)
    client = FakeDraftPrClient()

    result = create_manually_approved_draft_pr(
        policy_manifest_path=policy["manifest_path"],
        data_root=data_root,
        pr_client=client,
        approval_status="approved",
        explicit_decision="approve",
        confirmation_token_present=True,
        confirmation_text="CREATE DRAFT PR",
    )

    assert result["status"] == "created"
    assert result["draft_pr_created"] is True
    assert result["draft_pr_number"] == 134
    assert result["head_branch"] == branch["branch_name"]
    assert result["push_performed"] is False
    assert result["pr_update_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    assert client.calls == [
        {
            "base_ref": "main",
            "head_branch": branch["branch_name"],
            "title": client.calls[0]["title"],
            "body": client.calls[0]["body"],
        }
    ]
    stored = read_draft_pr_creation_result(result_path=result["result_path"], data_root=data_root)["result"]
    assert stored["schema_version"] == "atlas.draft_pr_creation_result.v1"
    assert stored["draft"] is True
    proposal_manifest = read_local_branch_proposal(
        manifest_path=Path(policy["manifest_path"]).parent / "manifest.json",
        data_root=data_root,
    )["manifest"]
    assert proposal_manifest["draft_pr_policy_status"] == "created"


def test_create_manually_approved_draft_pr_blocks_without_approval_or_client(tmp_path: Path) -> None:
    data_root, policy, _branch = _create_policy(tmp_path)

    result = create_manually_approved_draft_pr(policy_manifest_path=policy["manifest_path"], data_root=data_root)

    assert result["status"] == "blocked"
    assert "explicit_human_approval_required" in result["blocked_reasons"]
    assert "confirmation_token_required" in result["blocked_reasons"]
    assert "confirmation_text_mismatch" in result["blocked_reasons"]
    assert "draft_pr_client_required" in result["blocked_reasons"]
    assert result["draft_pr_created"] is False
    assert not Path(result["result_path"]).exists()


def test_create_manually_approved_draft_pr_dry_run_does_not_call_client_or_write(tmp_path: Path) -> None:
    data_root, policy, _branch = _create_policy(tmp_path)
    client = FakeDraftPrClient()

    result = create_manually_approved_draft_pr(
        policy_manifest_path=policy["manifest_path"],
        data_root=data_root,
        pr_client=client,
        approval_status="approved",
        explicit_decision="approve",
        confirmation_token_present=True,
        confirmation_text="CREATE DRAFT PR",
        dry_run=True,
    )

    assert result["status"] == "planned"
    assert result["draft_pr_created"] is False
    assert client.calls == []
    assert not Path(result["result_path"]).exists()


def test_create_manually_approved_draft_pr_rejects_non_draft_client_response(tmp_path: Path) -> None:
    data_root, policy, _branch = _create_policy(tmp_path)

    class BadClient:
        def create_draft_pull_request(self, **_kwargs: object) -> dict[str, object]:
            return {"number": 1, "html_url": "https://example.test/pr/1", "draft": False}

    result = create_manually_approved_draft_pr(
        policy_manifest_path=policy["manifest_path"],
        data_root=data_root,
        pr_client=BadClient(),
        approval_status="approved",
        explicit_decision="approve",
        confirmation_token_present=True,
        confirmation_text="CREATE DRAFT PR",
    )

    assert result["status"] == "blocked"
    assert result["blocked_reasons"] == ["draft_pr_must_be_draft"]
    assert not Path(result["result_path"]).exists()


def test_no_network_or_process_execution_in_draft_pr_creation_source() -> None:
    text = Path("app/atlas/draft_pr_creation.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
