import json
from pathlib import Path

import pytest

from app.atlas.fully_autonomous_code_agent_milestone import (
    REQUIRED_CONFIRMATION_TEXT,
    create_fully_autonomous_code_agent_milestone,
    validate_fully_autonomous_code_agent_milestone,
)
from app.atlas.self_improvement_autonomous_candidate_loop import validate_self_improvement_autonomous_candidate_loop


def _candidate_loop(data_root: Path, *, status: str = "ready") -> Path:
    candidate_root = data_root / "candidate_repo"
    stable_root = data_root.parent / "stable_repo"
    candidate_root.mkdir(parents=True, exist_ok=True)
    stable_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "atlas.self_improvement_autonomous_candidate_loop.v1",
        "candidate_loop_id": "candidate_loop_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-159",
        "next_required_pr": "PR-ATLAS-SCALE-160",
        "status": status,
        "blocking_reasons": [] if status == "ready" else ["blocked_for_test"],
        "previous_runtime_level": "level_6_full_automation_mode_checkpoint",
        "runtime_level": "level_7_self_improvement_autonomous_candidate_loop" if status == "ready" else "level_6_full_automation_mode_checkpoint",
        "target_runtime_level": "level_7_self_improvement_autonomous_candidate_loop",
        "runtime_transition_authorized": status == "ready",
        "backend_authoritative": True,
        "reviewer": "atlas",
        "full_automation_checkpoint_path": str(data_root / "atlas" / "full_auto" / "manifest.json"),
        "full_automation_checkpoint_schema_version": "atlas.full_automation_mode_checkpoint.v1",
        "full_automation_checkpoint_track_pr": "PR-ATLAS-SCALE-158",
        "full_automation_checkpoint_next_required_pr": "PR-ATLAS-SCALE-159",
        "full_automation_mode_ready": status == "ready",
        "candidate_root": str(candidate_root),
        "target_repo": str(stable_root),
        "loop_goal": "autonomously prepare the next candidate patch for Atlas",
        "allowed_candidate_actions": ["read_candidate_state", "request_failure_recovery_plan"] if status == "ready" else [],
        "max_iterations": 2,
        "checkpoint_evidence_refs": ["atlas/candidate-loop/evidence.json"] if status == "ready" else [],
        "candidate_workspace_only": True,
        "autonomous_candidate_loop_enabled": status == "ready",
        "self_improvement_autonomous_candidate_loop_enabled": status == "ready",
        "stop_on_gate_failure": True,
        "recovery_plan_required_before_promotion": True,
        "human_review_required_for_stable_mutation": True,
        "candidate_patch_preview_enabled": status == "ready",
        "candidate_verification_gate_request_enabled": status == "ready",
        "candidate_promotion_gate_request_enabled": status == "ready",
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "patch_apply_to_stable_runtime_enabled": False,
        "self_apply_enabled": False,
        "self_apply_performed": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "direct_merge_performed": False,
        "remote_git_push_enabled": False,
        "remote_git_push_performed": False,
        "release_pointer_switch_performed": False,
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "recovery_execution_performed": False,
        "arbitrary_command_execution_enabled": False,
        "execute_all_enabled": False,
        "default_ui_promotion_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
    }
    validate_self_improvement_autonomous_candidate_loop(payload)
    path = data_root / "atlas" / "self_improvement_autonomous_candidate_loops" / "candidate_loop_1" / "manifest.json"
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


def test_fully_autonomous_code_agent_milestone_ready_without_direct_merge_or_self_apply(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    loop_path = _candidate_loop(data_root)

    milestone = create_fully_autonomous_code_agent_milestone(
        autonomous_candidate_loop_path=loop_path,
        data_root=data_root,
        milestone_evidence_refs=["atlas/fully-autonomous/milestone.json"],
        rollback_evidence_refs=["atlas/fully-autonomous/rollback.json"],
        **_approved_kwargs(),
    )

    assert milestone["status"] == "ready"
    assert milestone["track_pr"] == "PR-ATLAS-SCALE-160"
    assert milestone["next_required_pr"] == "POST-SCALE-160-CONTINUOUS-IMPROVEMENT"
    assert milestone["runtime_level"] == "level_8_fully_autonomous_code_agent"
    assert milestone["runtime_transition_authorized"] is True
    assert milestone["fully_autonomous_code_agent_milestone_enabled"] is True
    assert milestone["fully_autonomous_code_agent_ready"] is True
    assert milestone["continuous_improvement_loop_ready"] is True
    assert milestone["separate_default_ui_promotion_required"] is True
    assert milestone["separate_stable_runtime_mutation_gate_required"] is True
    assert milestone["separate_direct_merge_gate_required"] is True
    assert milestone["stable_runtime_mutation_enabled"] is False
    assert milestone["direct_merge_enabled"] is False
    assert milestone["remote_git_push_enabled"] is False
    assert milestone["self_apply_enabled"] is False
    assert milestone["vue_authoritative"] is False
    assert milestone["execute_all_enabled"] is False


def test_fully_autonomous_code_agent_milestone_requires_ready_candidate_loop(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    loop_path = _candidate_loop(data_root, status="blocked")

    milestone = create_fully_autonomous_code_agent_milestone(
        autonomous_candidate_loop_path=loop_path,
        data_root=data_root,
        milestone_evidence_refs=["atlas/fully-autonomous/milestone.json"],
        rollback_evidence_refs=["atlas/fully-autonomous/rollback.json"],
        **_approved_kwargs(),
    )

    assert milestone["status"] == "blocked"
    assert "ready_autonomous_candidate_loop_required" in milestone["blocking_reasons"]
    assert "autonomous_candidate_loop_ready_required" in milestone["blocking_reasons"]
    assert milestone["runtime_level"] == "level_7_self_improvement_autonomous_candidate_loop"
    assert milestone["fully_autonomous_code_agent_ready"] is False


def test_fully_autonomous_code_agent_milestone_requires_evidence_and_confirmation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    loop_path = _candidate_loop(data_root)

    milestone = create_fully_autonomous_code_agent_milestone(
        autonomous_candidate_loop_path=loop_path,
        data_root=data_root,
        milestone_evidence_refs=["../outside.json"],
        rollback_evidence_refs=[],
        strict_gate_approved=False,
        confirmation_token_present=False,
        confirmation_text="AUTHORIZE",
        approval_status="approved",
        explicit_decision="approve",
    )

    assert milestone["status"] == "blocked"
    assert "milestone_evidence_refs_must_be_relative" in milestone["blocking_reasons"]
    assert "milestone_evidence_refs_required" in milestone["blocking_reasons"]
    assert "rollback_evidence_refs_required" in milestone["blocking_reasons"]
    assert "strict_gate_approval_required" in milestone["blocking_reasons"]
    assert "confirmation_token_required" in milestone["blocking_reasons"]
    assert "confirmation_text_mismatch" in milestone["blocking_reasons"]


def test_validate_fully_autonomous_code_agent_milestone_rejects_authority_escalation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    loop_path = _candidate_loop(data_root)
    milestone = create_fully_autonomous_code_agent_milestone(
        autonomous_candidate_loop_path=loop_path,
        data_root=data_root,
        milestone_evidence_refs=["atlas/fully-autonomous/milestone.json"],
        rollback_evidence_refs=["atlas/fully-autonomous/rollback.json"],
        **_approved_kwargs(),
    )
    milestone["direct_merge_enabled"] = True

    with pytest.raises(ValueError, match="invariant_violation:direct_merge_enabled"):
        validate_fully_autonomous_code_agent_milestone(milestone)


def test_fully_autonomous_code_agent_milestone_source_has_no_process_or_network_dependency() -> None:
    text = Path("app/atlas/fully_autonomous_code_agent_milestone.py").read_text(encoding="utf-8")
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
