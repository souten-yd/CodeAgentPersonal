import json
from pathlib import Path

import pytest

from app.atlas.full_automation_mode_checkpoint import validate_full_automation_mode_checkpoint
from app.atlas.self_improvement_autonomous_candidate_loop import (
    REQUIRED_CONFIRMATION_TEXT,
    create_self_improvement_autonomous_candidate_loop,
    validate_self_improvement_autonomous_candidate_loop,
)


def _checkpoint(data_root: Path, *, status: str = "ready") -> Path:
    payload = {
        "schema_version": "atlas.full_automation_mode_checkpoint.v1",
        "checkpoint_id": "full_auto_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-158",
        "next_required_pr": "PR-ATLAS-SCALE-159",
        "status": status,
        "blocking_reasons": [] if status == "ready" else ["blocked_for_test"],
        "previous_runtime_level": "level_5_autonomous_loop_execution_v1",
        "runtime_level": "level_6_full_automation_mode_checkpoint" if status == "ready" else "level_5_autonomous_loop_execution_v1",
        "target_runtime_level": "level_6_full_automation_mode_checkpoint",
        "runtime_transition_authorized": status == "ready",
        "backend_authoritative": True,
        "reviewer": "atlas",
        "autonomous_loop_execution_path": str(data_root / "atlas" / "loop" / "manifest.json"),
        "autonomous_loop_schema_version": "atlas.autonomous_loop_execution_v1.v1",
        "autonomous_loop_track_pr": "PR-ATLAS-SCALE-157",
        "autonomous_loop_next_required_pr": "PR-ATLAS-SCALE-158",
        "autonomous_loop_runtime_level": "level_5_autonomous_loop_execution_v1",
        "autonomous_loop_execution_ready": status == "ready",
        "checkpoint_evidence_refs": ["atlas/full_automation/checkpoint-evidence.json"] if status == "ready" else [],
        "full_automation_mode_checkpoint_enabled": status == "ready",
        "full_automation_mode_ready": status == "ready",
        "bounded_autonomous_execution_required": True,
        "recovery_plan_required": True,
        "human_review_required_for_stable_mutation": True,
        "arbitrary_command_execution_enabled": False,
        "command_execution_enabled": False,
        "direct_merge_enabled": False,
        "direct_merge_performed": False,
        "remote_git_push_enabled": False,
        "remote_git_push_performed": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "self_apply_enabled": False,
        "self_apply_performed": False,
        "self_modification_enabled": False,
        "release_pointer_switch_performed": False,
        "recovery_execution_performed": False,
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "default_ui_promotion_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "execute_all_enabled": False,
    }
    validate_full_automation_mode_checkpoint(payload)
    path = data_root / "atlas" / "full_automation_mode_checkpoints" / "full_auto_1" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _approved_kwargs() -> dict[str, object]:
    return {
        "strict_gate_approved": True,
        "confirmation_token_present": True,
        "confirmation_text": REQUIRED_CONFIRMATION_TEXT,
        "approval_status": "approved",
        "explicit_decision": "approve",
    }


def test_autonomous_candidate_loop_ready_without_stable_runtime_mutation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    candidate_root = data_root / "candidate_repo"
    target_repo = tmp_path / "stable_repo"
    candidate_root.mkdir(parents=True)
    target_repo.mkdir(parents=True)
    checkpoint_path = _checkpoint(data_root)

    loop = create_self_improvement_autonomous_candidate_loop(
        full_automation_checkpoint_path=checkpoint_path,
        data_root=data_root,
        candidate_root=candidate_root,
        target_repo=target_repo,
        loop_goal="autonomously prepare the next candidate patch for Atlas",
        max_iterations=3,
        checkpoint_evidence_refs=["atlas/candidate-loop/evidence.json"],
        allowed_candidate_actions=[
            "read_candidate_state",
            "prepare_candidate_patch_preview",
            "request_candidate_verification_gate",
            "request_candidate_promotion_gate",
            "request_failure_recovery_plan",
            "record_candidate_loop_report",
            "stop_on_gate_failure",
        ],
        **_approved_kwargs(),
    )

    assert loop["status"] == "ready"
    assert loop["track_pr"] == "PR-ATLAS-SCALE-159"
    assert loop["next_required_pr"] == "PR-ATLAS-SCALE-160"
    assert loop["runtime_level"] == "level_7_self_improvement_autonomous_candidate_loop"
    assert loop["runtime_transition_authorized"] is True
    assert loop["candidate_workspace_only"] is True
    assert loop["self_improvement_autonomous_candidate_loop_enabled"] is True
    assert loop["candidate_patch_preview_enabled"] is True
    assert loop["candidate_verification_gate_request_enabled"] is True
    assert loop["candidate_promotion_gate_request_enabled"] is True
    assert loop["stable_runtime_mutation_enabled"] is False
    assert loop["direct_merge_enabled"] is False
    assert loop["remote_git_push_enabled"] is False
    assert loop["self_apply_enabled"] is False
    assert loop["vue_authoritative"] is False
    assert loop["execute_all_enabled"] is False


def test_autonomous_candidate_loop_requires_ready_full_automation_checkpoint(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    candidate_root = data_root / "candidate_repo"
    target_repo = tmp_path / "stable_repo"
    candidate_root.mkdir(parents=True)
    target_repo.mkdir(parents=True)
    checkpoint_path = _checkpoint(data_root, status="blocked")

    loop = create_self_improvement_autonomous_candidate_loop(
        full_automation_checkpoint_path=checkpoint_path,
        data_root=data_root,
        candidate_root=candidate_root,
        target_repo=target_repo,
        loop_goal="continue Atlas",
        checkpoint_evidence_refs=["atlas/candidate-loop/evidence.json"],
        **_approved_kwargs(),
    )

    assert loop["status"] == "blocked"
    assert "ready_full_automation_checkpoint_required" in loop["blocking_reasons"]
    assert "full_automation_mode_ready_required" in loop["blocking_reasons"]
    assert loop["runtime_level"] == "level_6_full_automation_mode_checkpoint"
    assert loop["self_improvement_autonomous_candidate_loop_enabled"] is False


def test_autonomous_candidate_loop_rejects_stable_target_candidate_root_and_unsafe_actions(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    candidate_root = data_root / "stable_repo"
    candidate_root.mkdir(parents=True)
    checkpoint_path = _checkpoint(data_root)

    loop = create_self_improvement_autonomous_candidate_loop(
        full_automation_checkpoint_path=checkpoint_path,
        data_root=data_root,
        candidate_root=candidate_root,
        target_repo=candidate_root,
        loop_goal="continue Atlas",
        allowed_candidate_actions=["execute_shell"],
        max_iterations=4,
        checkpoint_evidence_refs=["../outside.json"],
        stop_on_gate_failure=False,
        require_recovery_plan_before_promotion=False,
        **_approved_kwargs(),
    )

    assert loop["status"] == "blocked"
    assert "candidate_root_must_not_be_stable_target_repo" in loop["blocking_reasons"]
    assert "candidate_loop_action_not_allowed" in loop["blocking_reasons"]
    assert "max_iterations_must_be_1_to_3" in loop["blocking_reasons"]
    assert "checkpoint_evidence_refs_must_be_relative" in loop["blocking_reasons"]
    assert "checkpoint_evidence_refs_required" in loop["blocking_reasons"]
    assert "stop_on_gate_failure_required" in loop["blocking_reasons"]
    assert "recovery_plan_before_promotion_required" in loop["blocking_reasons"]


def test_validate_autonomous_candidate_loop_rejects_authority_escalation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    candidate_root = data_root / "candidate_repo"
    target_repo = tmp_path / "stable_repo"
    candidate_root.mkdir(parents=True)
    target_repo.mkdir(parents=True)
    checkpoint_path = _checkpoint(data_root)
    loop = create_self_improvement_autonomous_candidate_loop(
        full_automation_checkpoint_path=checkpoint_path,
        data_root=data_root,
        candidate_root=candidate_root,
        target_repo=target_repo,
        loop_goal="continue Atlas",
        checkpoint_evidence_refs=["atlas/candidate-loop/evidence.json"],
        **_approved_kwargs(),
    )
    loop["remote_git_push_enabled"] = True

    with pytest.raises(ValueError, match="invariant_violation:remote_git_push_enabled"):
        validate_self_improvement_autonomous_candidate_loop(loop)


def test_autonomous_candidate_loop_source_has_no_process_or_network_dependency() -> None:
    text = Path("app/atlas/self_improvement_autonomous_candidate_loop.py").read_text(encoding="utf-8")
    forbidden = [
        "subprocess",
        "os.system",
        "requests",
        "from fastapi",
        "import fastapi",
        "uvicorn",
        "safe_apply",
        "self_apply_to_stable_runtime",
    ]
    for needle in forbidden:
        assert needle not in text
