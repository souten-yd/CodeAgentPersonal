import json
from pathlib import Path

from app.atlas.bounded_retry_recovery import create_bounded_retry_recovery_metadata, read_bounded_retry_recovery_metadata


def _write_policy(tmp_path: Path, overrides: dict[str, object] | None = None) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    policy_dir = data_root / "atlas" / "branch_proposals" / "proposal_1"
    policy_dir.mkdir(parents=True)
    payload: dict[str, object] = {
        "schema_version": "atlas.bounded_loop_policy.v1",
        "status": "created",
        "policy_id": "policy_1",
        "transaction_id": "txn_1",
        "draft_pr_number": 137,
        "changed_files": ["a.txt"],
        "policy_only": True,
        "max_iterations": 2,
        "loop_execution_enabled": False,
        "bounded_retry_enabled": False,
        "autonomous_execution_enabled": False,
        "self_modification_enabled": False,
        "requires_human_approval_each_iteration": True,
    }
    if overrides:
        payload.update(overrides)
    path = policy_dir / "bounded_loop_policy.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return data_root, path


def test_create_bounded_retry_recovery_metadata_writes_metadata_only_artifact(tmp_path: Path) -> None:
    data_root, policy_path = _write_policy(tmp_path)

    result = create_bounded_retry_recovery_metadata(
        bounded_loop_policy_path=policy_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        max_retries=2,
        failure_classes=["verification_failed", "policy_blocked"],
    )

    assert result["status"] == "created"
    assert result["metadata_only"] is True
    assert result["max_retries"] == 2
    assert result["retry_execution_enabled"] is False
    assert result["failure_recovery_execution_enabled"] is False
    assert result["auto_continue_enabled"] is False
    assert result["execute_all_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    metadata = read_bounded_retry_recovery_metadata(metadata_path=result["metadata_path"], data_root=data_root)["metadata"]
    assert metadata["schema_version"] == "atlas.bounded_retry_recovery.v1"
    assert "retry_without_human_approval" in metadata["forbidden_recovery_actions"]
    updated_policy = json.loads(policy_path.read_text(encoding="utf-8"))
    assert updated_policy["bounded_retry_recovery_status"] == "created"
    assert updated_policy["retry_execution_enabled"] is False


def test_create_bounded_retry_recovery_metadata_blocks_without_approval(tmp_path: Path) -> None:
    data_root, policy_path = _write_policy(tmp_path)

    result = create_bounded_retry_recovery_metadata(bounded_loop_policy_path=policy_path, data_root=data_root)

    assert result["status"] == "blocked"
    assert "explicit_human_approval_required" in result["blocked_reasons"]
    assert result["retry_execution_enabled"] is False
    assert not Path(result["metadata_path"]).exists()


def test_create_bounded_retry_recovery_metadata_blocks_out_of_bounds_retry(tmp_path: Path) -> None:
    data_root, policy_path = _write_policy(tmp_path)

    result = create_bounded_retry_recovery_metadata(
        bounded_loop_policy_path=policy_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        max_retries=3,
    )

    assert result["status"] == "blocked"
    assert "max_retries_out_of_bounds" in result["blocked_reasons"]
    assert not Path(result["metadata_path"]).exists()


def test_create_bounded_retry_recovery_metadata_blocks_untrusted_policy(tmp_path: Path) -> None:
    data_root, policy_path = _write_policy(
        tmp_path,
        {"loop_execution_enabled": True, "bounded_retry_enabled": True, "autonomous_execution_enabled": True},
    )

    result = create_bounded_retry_recovery_metadata(
        bounded_loop_policy_path=policy_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
    )

    assert result["status"] == "blocked"
    assert "loop_execution_enabled_must_be_false" in result["blocked_reasons"]
    assert "bounded_retry_must_not_be_pre_enabled" in result["blocked_reasons"]
    assert "autonomous_execution_enabled_must_be_false" in result["blocked_reasons"]


def test_create_bounded_retry_recovery_metadata_blocks_unknown_failure_class(tmp_path: Path) -> None:
    data_root, policy_path = _write_policy(tmp_path)

    result = create_bounded_retry_recovery_metadata(
        bounded_loop_policy_path=policy_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        failure_classes=["unknown_failure"],
    )

    assert result["status"] == "blocked"
    assert "failure_class_not_allowed" in result["blocked_reasons"]


def test_create_bounded_retry_recovery_metadata_dry_run_does_not_write(tmp_path: Path) -> None:
    data_root, policy_path = _write_policy(tmp_path)

    result = create_bounded_retry_recovery_metadata(
        bounded_loop_policy_path=policy_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        dry_run=True,
    )

    assert result["status"] == "planned"
    assert result["retry_execution_enabled"] is False
    assert not Path(result["metadata_path"]).exists()


def test_no_network_or_process_execution_in_bounded_retry_recovery_source() -> None:
    text = Path("app/atlas/bounded_retry_recovery.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
