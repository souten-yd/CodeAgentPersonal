import json
from pathlib import Path

import pytest

from app.atlas.autonomous_loop_execution_v1 import validate_autonomous_loop_execution_v1
from app.atlas.full_automation_mode_checkpoint import (
    REQUIRED_CONFIRMATION_TEXT,
    create_full_automation_mode_checkpoint,
    validate_full_automation_mode_checkpoint,
)


def _loop_session(data_root: Path, *, status: str = "ready") -> Path:
    payload = {
        "schema_version": "atlas.autonomous_loop_execution_v1.v1",
        "session_id": "loop_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-157",
        "next_required_pr": "PR-ATLAS-SCALE-158",
        "status": status,
        "blocking_reasons": [] if status == "ready" else ["blocked_for_test"],
        "previous_runtime_level": "level_4_self_improvement_platform",
        "runtime_level": "level_5_autonomous_loop_execution_v1" if status == "ready" else "level_4_self_improvement_platform",
        "target_runtime_level": "level_5_autonomous_loop_execution_v1",
        "runtime_transition_authorized": status == "ready",
        "backend_authoritative": True,
        "reviewer": "atlas",
        "loop_goal": "continue Atlas SCALE roadmap through the next gated candidate step",
        "automation_safety_profile_path": str(data_root / "atlas" / "profiles" / "manifest.json"),
        "automation_safety_profile_schema_version": "atlas.automation_safety_profile.v1",
        "automation_safety_profile_track_pr": "PR-ATLAS-SCALE-147",
        "automation_safety_profile": "autonomous_dev_agent",
        "automatic_failure_recovery_plan_path": str(data_root / "atlas" / "recovery" / "manifest.json"),
        "automatic_failure_recovery_schema_version": "atlas.self_improvement_automatic_failure_recovery.v1",
        "automatic_failure_recovery_track_pr": "PR-ATLAS-SCALE-156",
        "automatic_failure_recovery_ready": status == "ready",
        "allowed_loop_actions": ["read_backend_state", "select_next_candidate_step", "request_recovery_plan"] if status == "ready" else [],
        "max_iterations": 2,
        "bounded_loop_execution": True,
        "stop_on_failure": True,
        "recovery_plan_required_before_each_iteration": True,
        "human_review_required_for_stable_mutation": True,
        "autonomous_execution_enabled": status == "ready",
        "autonomous_loop_execution_enabled": status == "ready",
        "autonomous_loop_execution_v1_enabled": status == "ready",
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "arbitrary_command_execution_enabled": False,
        "patch_apply_to_stable_runtime_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "self_apply_enabled": False,
        "self_apply_performed": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "direct_merge_performed": False,
        "remote_git_push_enabled": False,
        "remote_git_push_performed": False,
        "release_pointer_switch_performed": False,
        "recovery_execution_performed": False,
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "default_ui_promotion_enabled": False,
        "llm_recovery_enabled": False,
        "execute_all_enabled": False,
    }
    validate_autonomous_loop_execution_v1(payload)
    path = data_root / "atlas" / "autonomous_loop_execution_v1" / "loop_1" / "manifest.json"
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


def test_full_automation_mode_checkpoint_ready_without_direct_merge_or_stable_mutation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    loop_path = _loop_session(data_root)

    checkpoint = create_full_automation_mode_checkpoint(
        autonomous_loop_execution_path=loop_path,
        data_root=data_root,
        checkpoint_evidence_refs=["atlas/full_automation/checkpoint-evidence.json"],
        **_approved_kwargs(),
    )

    assert checkpoint["status"] == "ready"
    assert checkpoint["track_pr"] == "PR-ATLAS-SCALE-158"
    assert checkpoint["next_required_pr"] == "PR-ATLAS-SCALE-159"
    assert checkpoint["runtime_level"] == "level_6_full_automation_mode_checkpoint"
    assert checkpoint["runtime_transition_authorized"] is True
    assert checkpoint["full_automation_mode_checkpoint_enabled"] is True
    assert checkpoint["full_automation_mode_ready"] is True
    assert checkpoint["bounded_autonomous_execution_required"] is True
    assert checkpoint["recovery_plan_required"] is True
    assert checkpoint["arbitrary_command_execution_enabled"] is False
    assert checkpoint["command_execution_enabled"] is False
    assert checkpoint["direct_merge_enabled"] is False
    assert checkpoint["remote_git_push_enabled"] is False
    assert checkpoint["stable_runtime_mutation_enabled"] is False
    assert checkpoint["self_apply_enabled"] is False
    assert checkpoint["vue_authoritative"] is False
    assert checkpoint["execute_all_enabled"] is False


def test_full_automation_mode_checkpoint_requires_ready_autonomous_loop(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    loop_path = _loop_session(data_root, status="blocked")

    checkpoint = create_full_automation_mode_checkpoint(
        autonomous_loop_execution_path=loop_path,
        data_root=data_root,
        checkpoint_evidence_refs=["atlas/full_automation/checkpoint-evidence.json"],
        **_approved_kwargs(),
    )

    assert checkpoint["status"] == "blocked"
    assert "ready_autonomous_loop_required" in checkpoint["blocking_reasons"]
    assert "autonomous_loop_execution_v1_required" in checkpoint["blocking_reasons"]
    assert checkpoint["runtime_level"] == "level_5_autonomous_loop_execution_v1"
    assert checkpoint["full_automation_mode_checkpoint_enabled"] is False


def test_full_automation_mode_checkpoint_requires_evidence_and_confirmation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    loop_path = _loop_session(data_root)

    checkpoint = create_full_automation_mode_checkpoint(
        autonomous_loop_execution_path=loop_path,
        data_root=data_root,
        checkpoint_evidence_refs=["../outside.json"],
        strict_gate_approved=False,
        confirmation_token_present=False,
        confirmation_text="AUTHORIZE",
        approval_status="approved",
        explicit_decision="approve",
    )

    assert checkpoint["status"] == "blocked"
    assert "checkpoint_evidence_refs_must_be_relative" in checkpoint["blocking_reasons"]
    assert "checkpoint_evidence_refs_required" in checkpoint["blocking_reasons"]
    assert "strict_gate_approval_required" in checkpoint["blocking_reasons"]
    assert "confirmation_token_required" in checkpoint["blocking_reasons"]
    assert "confirmation_text_mismatch" in checkpoint["blocking_reasons"]


def test_validate_full_automation_mode_checkpoint_rejects_authority_escalation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    loop_path = _loop_session(data_root)
    checkpoint = create_full_automation_mode_checkpoint(
        autonomous_loop_execution_path=loop_path,
        data_root=data_root,
        checkpoint_evidence_refs=["atlas/full_automation/checkpoint-evidence.json"],
        **_approved_kwargs(),
    )
    checkpoint["stable_runtime_mutation_enabled"] = True

    with pytest.raises(ValueError, match="invariant_violation:stable_runtime_mutation_enabled"):
        validate_full_automation_mode_checkpoint(checkpoint)


def test_full_automation_mode_checkpoint_source_has_no_process_or_network_dependency() -> None:
    text = Path("app/atlas/full_automation_mode_checkpoint.py").read_text(encoding="utf-8")
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
