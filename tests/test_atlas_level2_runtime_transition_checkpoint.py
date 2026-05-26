import json
from pathlib import Path

from app.atlas.level2_runtime_transition_checkpoint import (
    create_level2_runtime_transition_checkpoint,
    load_level2_runtime_transition_checkpoint,
    write_level2_runtime_transition_checkpoint,
)


def _write_inputs(tmp_path: Path, *, policy_overrides: dict[str, object] | None = None, retry_overrides: dict[str, object] | None = None) -> tuple[Path, Path, Path]:
    data_root = tmp_path / "data"
    proposal_dir = data_root / "atlas" / "branch_proposals" / "proposal_1"
    proposal_dir.mkdir(parents=True)
    policy: dict[str, object] = {
        "schema_version": "atlas.bounded_loop_policy.v1",
        "status": "created",
        "policy_id": "policy_1",
        "transaction_id": "txn_1",
        "draft_pr_number": 138,
        "changed_files": ["a.txt"],
        "policy_only": True,
        "max_iterations": 2,
        "loop_execution_enabled": False,
        "bounded_retry_enabled": False,
        "autonomous_execution_enabled": False,
        "self_modification_enabled": False,
        "requires_human_approval_each_iteration": True,
    }
    if policy_overrides:
        policy.update(policy_overrides)
    retry: dict[str, object] = {
        "schema_version": "atlas.bounded_retry_recovery.v1",
        "status": "created",
        "metadata_only": True,
        "policy_id": policy["policy_id"],
        "transaction_id": "txn_1",
        "draft_pr_number": 138,
        "changed_files": ["a.txt"],
        "max_retries": 1,
        "failure_classes": ["verification_failed"],
        "retry_execution_enabled": False,
        "failure_recovery_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "autonomous_execution_enabled": False,
        "requires_human_approval_before_retry": True,
    }
    if retry_overrides:
        retry.update(retry_overrides)
    policy_path = proposal_dir / "bounded_loop_policy.json"
    retry_path = proposal_dir / "bounded_retry_recovery.json"
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    retry_path.write_text(json.dumps(retry, indent=2), encoding="utf-8")
    return data_root, policy_path, retry_path


def test_create_level2_runtime_transition_checkpoint_authorizes_with_all_gates(tmp_path: Path) -> None:
    data_root, policy_path, retry_path = _write_inputs(tmp_path)

    checkpoint = create_level2_runtime_transition_checkpoint(
        bounded_loop_policy_path=policy_path,
        retry_recovery_metadata_path=retry_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        stop_gate_ready=True,
        verification_allowlist_ready=True,
        artifact_capture_ready=True,
    )

    assert checkpoint["transition_authorized"] is True
    assert checkpoint["runtime_level"] == "level_2_guarded_bounded_loop"
    assert checkpoint["previous_runtime_level"] == "level_1_guarded_single_step"
    assert checkpoint["level2_guarded_bounded_loop_enabled"] is True
    assert checkpoint["bounded_loop_execution_allowed"] is True
    assert checkpoint["autonomous_execution_enabled"] is False
    assert checkpoint["auto_continue_enabled"] is False
    assert checkpoint["execute_all_enabled"] is False
    assert checkpoint["vue_authoritative"] is False
    assert checkpoint["execution_performed"] is False


def test_create_level2_runtime_transition_checkpoint_allows_zero_retry_policy(tmp_path: Path) -> None:
    data_root, policy_path, retry_path = _write_inputs(tmp_path, retry_overrides={"max_retries": 0})

    checkpoint = create_level2_runtime_transition_checkpoint(
        bounded_loop_policy_path=policy_path,
        retry_recovery_metadata_path=retry_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        stop_gate_ready=True,
        verification_allowlist_ready=True,
        artifact_capture_ready=True,
    )

    assert checkpoint["transition_authorized"] is True
    assert checkpoint["max_retries"] == 0


def test_create_level2_runtime_transition_checkpoint_blocks_without_gates(tmp_path: Path) -> None:
    data_root, policy_path, retry_path = _write_inputs(tmp_path)

    checkpoint = create_level2_runtime_transition_checkpoint(
        bounded_loop_policy_path=policy_path,
        retry_recovery_metadata_path=retry_path,
        data_root=data_root,
    )

    assert checkpoint["transition_authorized"] is False
    assert checkpoint["runtime_level"] == "level_1_guarded_single_step"
    assert checkpoint["level2_guarded_bounded_loop_enabled"] is False
    assert "explicit_human_approval_required" in checkpoint["blocking_reasons"]
    assert "stop_gate_required" in checkpoint["blocking_reasons"]
    assert "verification_allowlist_required" in checkpoint["blocking_reasons"]
    assert "artifact_capture_required" in checkpoint["blocking_reasons"]


def test_create_level2_runtime_transition_checkpoint_blocks_untrusted_policy_or_retry(tmp_path: Path) -> None:
    data_root, policy_path, retry_path = _write_inputs(
        tmp_path,
        policy_overrides={"loop_execution_enabled": True, "autonomous_execution_enabled": True},
        retry_overrides={"retry_execution_enabled": True, "auto_continue_enabled": True},
    )

    checkpoint = create_level2_runtime_transition_checkpoint(
        bounded_loop_policy_path=policy_path,
        retry_recovery_metadata_path=retry_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        stop_gate_ready=True,
        verification_allowlist_ready=True,
        artifact_capture_ready=True,
    )

    assert checkpoint["transition_authorized"] is False
    assert "loop_execution_enabled_must_be_false" in checkpoint["blocking_reasons"]
    assert "autonomous_execution_enabled_must_be_false" in checkpoint["blocking_reasons"]
    assert "retry_execution_enabled_must_be_false" in checkpoint["blocking_reasons"]
    assert "auto_continue_enabled_must_be_false" in checkpoint["blocking_reasons"]


def test_write_and_load_level2_runtime_transition_checkpoint(tmp_path: Path) -> None:
    data_root, policy_path, retry_path = _write_inputs(tmp_path)
    checkpoint = create_level2_runtime_transition_checkpoint(
        bounded_loop_policy_path=policy_path,
        retry_recovery_metadata_path=retry_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        stop_gate_ready=True,
        verification_allowlist_ready=True,
        artifact_capture_ready=True,
    )

    path = write_level2_runtime_transition_checkpoint(data_root=data_root, checkpoint=checkpoint)
    loaded = load_level2_runtime_transition_checkpoint(manifest_path=path, data_root=data_root)

    assert loaded["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert loaded["runtime_level"] == "level_2_guarded_bounded_loop"


def test_no_network_or_process_execution_in_level2_checkpoint_source() -> None:
    text = Path("app/atlas/level2_runtime_transition_checkpoint.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
