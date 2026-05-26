import json
from pathlib import Path

from app.atlas.patch_transaction import create_patch_transaction
from app.atlas.self_improvement_patch_apply import (
    REQUIRED_CONFIRMATION_TEXT,
    apply_self_improvement_patch_one_action,
)


def _write_dry_run_verification(tmp_path: Path, *, data_root: Path, overrides: dict[str, object] | None = None) -> Path:
    verification_dir = data_root / "atlas" / "self_improvement_dry_run_verifications" / "verification_1"
    verification_dir.mkdir(parents=True)
    verification: dict[str, object] = {
        "schema_version": "atlas.self_improvement_dry_run_verification.v1",
        "verification_id": "verification_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-143",
        "next_required_pr": "PR-ATLAS-SCALE-144",
        "patch_preview_path": str(data_root / "preview.json"),
        "data_root": str(data_root),
        "project_path": str(tmp_path / "project"),
        "reviewer": "atlas",
        "target_repo": "KasaneCore",
        "target_area": "atlas_runtime",
        "risk_classification": "strict",
        "strict_gate_required": True,
        "verification_risk_level": "strict_gate",
        "proposed_commands": ["pytest -q tests/test_atlas_self_improvement_patch_apply.py"],
        "command_results": [
            {
                "command": "pytest -q tests/test_atlas_self_improvement_patch_apply.py",
                "allowed": True,
                "requires_human_approval": True,
            }
        ],
        "allowed_commands": ["pytest -q tests/test_atlas_self_improvement_patch_apply.py"],
        "blocked_commands": [],
        "dry_run_verification_authorized": True,
        "dry_run_verification_blocked": False,
        "blocking_reasons": [],
        "self_improvement_dry_run_verification_enabled": True,
        "dry_run_only": True,
        "verification_plan_only": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
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
        "allowed_verification_actions": ["read_patch_preview", "classify_commands", "record_dry_run_plan", "request_human_review"],
        "forbidden_verification_actions": ["execute_command", "apply_patch", "direct_merge"],
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
    if overrides:
        verification.update(overrides)
    path = verification_dir / "manifest.json"
    path.write_text(json.dumps(verification, indent=2), encoding="utf-8")
    return path


def _transaction(project: Path, data_root: Path) -> dict[str, object]:
    target = project / "a.txt"
    target.write_text("old\n", encoding="utf-8")
    return create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_1",
        snapshot_manifest_path="/tmp/snap_manifest.json",
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
        diff_text="diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n",
        risk_class="strict_gate",
    )


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


def test_self_improvement_patch_apply_blocks_without_required_gates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    verification_path = _write_dry_run_verification(tmp_path, data_root=data_root)
    txn = _transaction(project, data_root)

    result = apply_self_improvement_patch_one_action(
        dry_run_verification_path=verification_path,
        patch_transaction_manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
    )

    assert result["status"] == "blocked"
    assert "dry_run_gate_ready_required" in result["blocked_reasons"]
    assert "rollback_ready_required" in result["blocked_reasons"]
    assert "strict_gate_approval_required" in result["blocked_reasons"]
    assert "explicit_human_approval_required" in result["blocked_reasons"]
    assert (project / "a.txt").read_text(encoding="utf-8") == "old\n"
    assert result["automatic_patch_apply_enabled"] is False
    assert result["direct_merge_enabled"] is False
    assert result["remote_git_push_enabled"] is False


def test_self_improvement_patch_apply_dry_run_plans_without_mutation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    verification_path = _write_dry_run_verification(tmp_path, data_root=data_root)
    txn = _transaction(project, data_root)

    result = apply_self_improvement_patch_one_action(
        dry_run_verification_path=verification_path,
        patch_transaction_manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
        dry_run=True,
        **_approved_kwargs(),
    )

    assert result["status"] == "planned"
    assert result["changed_files"] == ["a.txt"]
    assert result["mutation_performed"] is False
    assert (project / "a.txt").read_text(encoding="utf-8") == "old\n"


def test_self_improvement_patch_apply_applies_single_approved_patch(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    verification_path = _write_dry_run_verification(tmp_path, data_root=data_root)
    txn = _transaction(project, data_root)

    result = apply_self_improvement_patch_one_action(
        dry_run_verification_path=verification_path,
        patch_transaction_manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
        **_approved_kwargs(),
    )

    assert result["status"] == "applied"
    assert result["changed_files"] == ["a.txt"]
    assert result["actual_file_changed"] is True
    assert result["mutation_performed"] is True
    assert result["self_apply_enabled"] is False
    assert result["automatic_patch_apply_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    assert result["direct_merge_enabled"] is False
    assert result["remote_git_push_enabled"] is False
    assert (project / "a.txt").read_text(encoding="utf-8") == "new\n"
    assert Path(result["apply_result_path"]).exists()
    assert Path(result["apply_result_path"]).is_relative_to(data_root)


def test_self_improvement_patch_apply_blocks_untrusted_verification(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    verification_path = _write_dry_run_verification(
        tmp_path,
        data_root=data_root,
        overrides={
            "dry_run_verification_authorized": False,
            "dry_run_verification_blocked": True,
            "self_improvement_dry_run_verification_enabled": False,
            "allowed_commands": [],
        },
    )
    txn = _transaction(project, data_root)

    result = apply_self_improvement_patch_one_action(
        dry_run_verification_path=verification_path,
        patch_transaction_manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
        **_approved_kwargs(),
    )

    assert result["status"] == "blocked"
    assert "authorized_dry_run_verification_required" in result["blocked_reasons"]
    assert "dry_run_verification_enabled_required" in result["blocked_reasons"]
    assert "allowed_verification_command_required" in result["blocked_reasons"]
    assert (project / "a.txt").read_text(encoding="utf-8") == "old\n"


def test_no_network_or_process_execution_in_self_improvement_patch_apply_source() -> None:
    text = Path("app/atlas/self_improvement_patch_apply.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
