import json
from pathlib import Path

from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.self_improvement_draft_pr_creation import (
    REQUIRED_CONFIRMATION_TEXT,
    create_self_improvement_draft_pr_one_action,
    load_self_improvement_draft_pr_creation,
)
from app.atlas.self_improvement_patch_apply import (
    REQUIRED_CONFIRMATION_TEXT as APPLY_CONFIRMATION_TEXT,
    apply_self_improvement_patch_one_action,
)


class FakeDraftPrClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_draft_pull_request(self, *, base_ref: str, head_branch: str, title: str, body: str) -> dict[str, object]:
        self.calls.append({"base_ref": base_ref, "head_branch": head_branch, "title": title, "body": body})
        return {"number": 145, "html_url": "https://example.test/pr/145", "url": "https://api.example.test/pr/145", "draft": True}


def _write_dry_run_verification(data_root: Path) -> Path:
    verification_dir = data_root / "atlas" / "self_improvement_dry_run_verifications" / "verify_1"
    verification_dir.mkdir(parents=True)
    manifest = {
        "schema_version": "atlas.self_improvement_dry_run_verification.v1",
        "verification_id": "verify_1",
        "track_pr": "PR-ATLAS-SCALE-143",
        "next_required_pr": "PR-ATLAS-SCALE-144",
        "dry_run_verification_authorized": True,
        "self_improvement_dry_run_verification_enabled": True,
        "strict_gate_required": True,
        "allowed_commands": ["pytest -q tests/test_atlas_self_improvement_draft_pr_creation.py"],
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


def _transaction(project: Path, data_root: Path) -> Path:
    target = project / "a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    diff = "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"
    created = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_1",
        snapshot_manifest_path=str(data_root / "snapshots" / "snap_1.json"),
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
        diff_text=diff,
        risk_class="strict_gate",
    )
    path = Path(str(created["manifest_path"]))
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["proposed_files"] = [
        {"relative_path": "a.txt", "change_type": "modify", "path_valid": True, "exists_before": True, "warnings": []}
    ]
    manifest["file_count"] = 1
    manifest["changed_file_count"] = 1
    manifest["diff_summary"]["total_files"] = 1
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def _apply_result_path(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    project = tmp_path / "project"
    verification = _write_dry_run_verification(data_root)
    transaction = _transaction(project, data_root)
    result = apply_self_improvement_patch_one_action(
        dry_run_verification_path=verification,
        patch_transaction_manifest_path=transaction,
        data_root=data_root,
        project_path=project,
        dry_run_gate_ready=True,
        rollback_ready=True,
        strict_gate_approved=True,
        confirmation_token_present=True,
        confirmation_text=APPLY_CONFIRMATION_TEXT,
        approval_status="approved",
        explicit_decision="approve",
    )
    return data_root, Path(str(result["apply_result_path"]))


def _approved_kwargs() -> dict[str, object]:
    return {
        "base_ref": "main",
        "head_branch": "codex/atlas-self-improvement-145",
        "title": "Atlas self-improvement draft PR",
        "body": "## Summary\n- Draft PR for one approved self-improvement patch.",
        "branch_ready_for_draft_pr": True,
        "strict_gate_approved": True,
        "approval_status": "approved",
        "explicit_decision": "approve",
        "confirmation_token_present": True,
        "confirmation_text": REQUIRED_CONFIRMATION_TEXT,
    }


def test_create_self_improvement_draft_pr_uses_injected_client(tmp_path: Path) -> None:
    data_root, apply_result = _apply_result_path(tmp_path)
    client = FakeDraftPrClient()

    result = create_self_improvement_draft_pr_one_action(
        apply_result_path=apply_result,
        data_root=data_root,
        pr_client=client,
        **_approved_kwargs(),
    )

    assert result["status"] == "created"
    assert result["draft_pr_created"] is True
    assert result["draft_pr_number"] == 145
    assert result["draft"] is True
    assert result["changed_files"] == ["a.txt"]
    assert result["remote_git_push_enabled"] is False
    assert result["direct_merge_enabled"] is False
    assert result["self_modification_enabled"] is False
    assert result["self_apply_enabled"] is False
    assert result["branch_created"] is False
    assert client.calls == [
        {
            "base_ref": "main",
            "head_branch": "codex/atlas-self-improvement-145",
            "title": "Atlas self-improvement draft PR",
            "body": "## Summary\n- Draft PR for one approved self-improvement patch.",
        }
    ]
    stored = load_self_improvement_draft_pr_creation(manifest_path=result["result_path"], data_root=data_root)
    assert stored["schema_version"] == "atlas.self_improvement_draft_pr_creation.v1"


def test_create_self_improvement_draft_pr_blocks_without_gates_or_client(tmp_path: Path) -> None:
    data_root, apply_result = _apply_result_path(tmp_path)

    result = create_self_improvement_draft_pr_one_action(
        apply_result_path=apply_result,
        data_root=data_root,
        base_ref="main",
        head_branch="codex/atlas-self-improvement-145",
        title="Atlas self-improvement draft PR",
        body="body",
    )

    assert result["status"] == "blocked"
    assert "branch_ready_for_draft_pr_required" in result["blocked_reasons"]
    assert "strict_gate_approval_required" in result["blocked_reasons"]
    assert "explicit_human_approval_required" in result["blocked_reasons"]
    assert "confirmation_token_required" in result["blocked_reasons"]
    assert "confirmation_text_mismatch" in result["blocked_reasons"]
    assert "draft_pr_client_required" in result["blocked_reasons"]
    assert result["draft_pr_created"] is False
    assert not Path(str(result["result_path"])).exists()


def test_create_self_improvement_draft_pr_dry_run_does_not_call_client_or_write(tmp_path: Path) -> None:
    data_root, apply_result = _apply_result_path(tmp_path)
    client = FakeDraftPrClient()

    result = create_self_improvement_draft_pr_one_action(
        apply_result_path=apply_result,
        data_root=data_root,
        pr_client=client,
        dry_run=True,
        **_approved_kwargs(),
    )

    assert result["status"] == "planned"
    assert result["draft_pr_created"] is False
    assert client.calls == []
    assert not Path(str(result["result_path"])).exists()


def test_create_self_improvement_draft_pr_rejects_non_draft_response(tmp_path: Path) -> None:
    data_root, apply_result = _apply_result_path(tmp_path)

    class BadClient:
        def create_draft_pull_request(self, **_kwargs: object) -> dict[str, object]:
            return {"number": 1, "html_url": "https://example.test/pr/1", "draft": False}

    result = create_self_improvement_draft_pr_one_action(
        apply_result_path=apply_result,
        data_root=data_root,
        pr_client=BadClient(),
        **_approved_kwargs(),
    )

    assert result["status"] == "blocked"
    assert result["blocked_reasons"] == ["draft_pr_must_be_draft"]
    assert result["draft_pr_created"] is False
    assert not Path(str(result["result_path"])).exists()


def test_no_network_or_process_execution_in_self_improvement_draft_pr_creation_source() -> None:
    text = Path("app/atlas/self_improvement_draft_pr_creation.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
