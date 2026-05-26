import json
from pathlib import Path

from app.atlas.level3_autonomous_loop_candidate import (
    create_level3_autonomous_loop_candidate,
    load_level3_autonomous_loop_candidate,
    write_level3_autonomous_loop_candidate,
)


def _write_level2_checkpoint(tmp_path: Path, *, overrides: dict[str, object] | None = None) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    checkpoint_dir = data_root / "atlas" / "level2_runtime_transition_checkpoints" / "checkpoint_1"
    checkpoint_dir.mkdir(parents=True)
    checkpoint: dict[str, object] = {
        "schema_version": "atlas.level2_runtime_transition_checkpoint.v1",
        "checkpoint_id": "checkpoint_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "transition_pr": "PR-ATLAS-SCALE-138",
        "next_required_pr": "PR-ATLAS-SCALE-139",
        "previous_runtime_level": "level_1_guarded_single_step",
        "runtime_level": "level_2_guarded_bounded_loop",
        "target_runtime_level": "level_2_guarded_bounded_loop",
        "transition_authorized": True,
        "transition_blocked": False,
        "blocking_reasons": [],
        "bounded_loop_policy_path": str(data_root / "policy.json"),
        "retry_recovery_metadata_path": str(data_root / "retry.json"),
        "data_root": str(data_root),
        "level2_guarded_bounded_loop_enabled": True,
        "bounded_loop_execution_allowed": True,
        "bounded_retry_candidate_allowed": True,
        "max_iterations": 2,
        "max_retries": 1,
        "single_changed_file_only": True,
        "low_risk_only": True,
        "dry_run_required_each_iteration": True,
        "explicit_approval_required_each_iteration": True,
        "stop_gate_required": True,
        "verification_allowlist_required": True,
        "artifact_capture_required": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "retry_performed": False,
        "verification_performed": False,
        "rollback_performed": False,
        "restore_performed": False,
    }
    if overrides:
        checkpoint.update(overrides)
    path = checkpoint_dir / "manifest.json"
    path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
    return data_root, path


def test_create_level3_autonomous_loop_candidate_authorizes_with_all_gates(tmp_path: Path) -> None:
    data_root, checkpoint_path = _write_level2_checkpoint(tmp_path)

    candidate = create_level3_autonomous_loop_candidate(
        level2_checkpoint_path=checkpoint_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        max_iterations=2,
        max_retries=1,
        verification_commands=["pytest", "atlas_smoke"],
    )

    assert candidate["candidate_authorized"] is True
    assert candidate["runtime_level"] == "level_3_autonomous_implementation_loop_candidate"
    assert candidate["previous_runtime_level"] == "level_2_guarded_bounded_loop"
    assert candidate["level3_autonomous_loop_candidate_enabled"] is True
    assert candidate["autonomous_loop_execution_enabled"] is False
    assert candidate["autonomous_execution_enabled"] is False
    assert candidate["automatic_patch_apply_enabled"] is False
    assert candidate["automatic_verification_enabled"] is False
    assert candidate["draft_pr_only"] is True
    assert candidate["direct_merge_enabled"] is False
    assert candidate["remote_git_push_enabled"] is False
    assert candidate["execution_performed"] is False
    assert candidate["mutation_performed"] is False


def test_create_level3_autonomous_loop_candidate_blocks_without_approval(tmp_path: Path) -> None:
    data_root, checkpoint_path = _write_level2_checkpoint(tmp_path)

    candidate = create_level3_autonomous_loop_candidate(level2_checkpoint_path=checkpoint_path, data_root=data_root)

    assert candidate["candidate_authorized"] is False
    assert candidate["runtime_level"] == "level_2_guarded_bounded_loop"
    assert candidate["level3_autonomous_loop_candidate_enabled"] is False
    assert "explicit_human_approval_required" in candidate["blocking_reasons"]


def test_create_level3_autonomous_loop_candidate_blocks_unsafe_bounds(tmp_path: Path) -> None:
    data_root, checkpoint_path = _write_level2_checkpoint(tmp_path)

    candidate = create_level3_autonomous_loop_candidate(
        level2_checkpoint_path=checkpoint_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        max_iterations=4,
        max_retries=3,
        max_changed_files=2,
        max_runtime_minutes=61,
        max_risk_level="medium",
        draft_pr_only=False,
    )

    assert candidate["candidate_authorized"] is False
    assert "max_iterations_out_of_bounds" in candidate["blocking_reasons"]
    assert "max_retries_out_of_bounds" in candidate["blocking_reasons"]
    assert "single_changed_file_required" in candidate["blocking_reasons"]
    assert "max_runtime_minutes_out_of_bounds" in candidate["blocking_reasons"]
    assert "max_risk_level_not_allowed" in candidate["blocking_reasons"]
    assert "draft_pr_only_required" in candidate["blocking_reasons"]


def test_create_level3_autonomous_loop_candidate_blocks_unapproved_level2_checkpoint(tmp_path: Path) -> None:
    data_root, checkpoint_path = _write_level2_checkpoint(
        tmp_path,
        overrides={
            "transition_authorized": False,
            "transition_blocked": True,
            "runtime_level": "level_1_guarded_single_step",
            "level2_guarded_bounded_loop_enabled": False,
            "bounded_loop_execution_allowed": False,
            "bounded_retry_candidate_allowed": False,
            "blocking_reasons": ["fixture_blocked"],
        },
    )

    candidate = create_level3_autonomous_loop_candidate(
        level2_checkpoint_path=checkpoint_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
    )

    assert candidate["candidate_authorized"] is False
    assert "level2_transition_authorization_required" in candidate["blocking_reasons"]
    assert "level2_runtime_level_required" in candidate["blocking_reasons"]
    assert "level2_guarded_bounded_loop_required" in candidate["blocking_reasons"]


def test_create_level3_autonomous_loop_candidate_blocks_unallowlisted_verification(tmp_path: Path) -> None:
    data_root, checkpoint_path = _write_level2_checkpoint(tmp_path)

    candidate = create_level3_autonomous_loop_candidate(
        level2_checkpoint_path=checkpoint_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        verification_commands=["pytest", "git push"],
    )

    assert candidate["candidate_authorized"] is False
    assert "verification_command_not_allowed" in candidate["blocking_reasons"]


def test_write_and_load_level3_autonomous_loop_candidate(tmp_path: Path) -> None:
    data_root, checkpoint_path = _write_level2_checkpoint(tmp_path)
    candidate = create_level3_autonomous_loop_candidate(
        level2_checkpoint_path=checkpoint_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
    )

    path = write_level3_autonomous_loop_candidate(data_root=data_root, candidate=candidate)
    loaded = load_level3_autonomous_loop_candidate(manifest_path=path, data_root=data_root)

    assert loaded["candidate_id"] == candidate["candidate_id"]
    assert loaded["runtime_level"] == "level_3_autonomous_implementation_loop_candidate"


def test_no_network_or_process_execution_in_level3_candidate_source() -> None:
    text = Path("app/atlas/level3_autonomous_loop_candidate.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
