import json
from pathlib import Path

import pytest

from app.atlas.automation_safety_profile import validate_automation_safety_profile
from app.atlas.autonomous_loop_execution_v1 import (
    REQUIRED_CONFIRMATION_TEXT,
    create_autonomous_loop_execution_v1,
    validate_autonomous_loop_execution_v1,
)
from app.atlas.self_improvement_automatic_failure_recovery import validate_automatic_failure_recovery_plan


def _safety_profile(data_root: Path, *, profile: str = "autonomous_dev_agent") -> Path:
    payload = {
        "schema_version": "atlas.automation_safety_profile.v1",
        "profile_id": "profile_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-147",
        "next_required_pr": "PR-ATLAS-SCALE-148",
        "status": "active",
        "blocking_reasons": [],
        "runtime_level": "level_4_self_improvement_platform",
        "automation_safety_profile": profile,
        "profile_rank": 3 if profile == "autonomous_dev_agent" else 2,
        "explicit_profile_selection_required": True,
        "explicit_profile_selection": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "self_improvement_enabled": True,
        "requested_self_improvement_enabled": True,
        "self_improvement_scope": "full_platform_strict",
        "strict_gate_required_for_self_improvement": True,
        "strict_gate_approved": True,
        "level4_checkpoint_required_for_self_improvement": True,
        "level4_checkpoint_path": str(data_root / "atlas" / "level4" / "manifest.json"),
        "automation_safety_profile_framework_enabled": True,
        "capabilities": {
            "allows_file_mutation": True,
            "allows_command_execution": True,
            "allows_patch_apply": True,
            "allows_git_mutation": True,
            "allows_branch_creation": True,
            "allows_draft_pr_creation": True,
            "allows_draft_pr_update": True,
            "allows_auto_continue": True,
            "allows_autonomous_loop_execution": True,
            "requires_human_approval_for_mutation": False,
            "max_risk_level": "medium",
        },
        "review_only": False,
        "guarded_single_action": False,
        "supervised_bounded_auto": False,
        "autonomous_dev_agent": profile == "autonomous_dev_agent",
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_applied": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
        "direct_merge_performed": False,
        "remote_git_push_performed": False,
        "stable_runtime_mutation_performed": False,
    }
    if profile != "autonomous_dev_agent":
        payload["automation_safety_profile"] = "supervised_bounded_auto"
        payload["profile_rank"] = 2
        payload["capabilities"]["allows_auto_continue"] = False
        payload["capabilities"]["allows_autonomous_loop_execution"] = False
        payload["capabilities"]["requires_human_approval_for_mutation"] = True
        payload["autonomous_dev_agent"] = False
        payload["supervised_bounded_auto"] = True
    validate_automation_safety_profile(payload)
    path = data_root / "atlas" / "automation_safety_profiles" / "profile_1" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _recovery_plan(data_root: Path, *, status: str = "ready") -> Path:
    payload = {
        "schema_version": "atlas.self_improvement_automatic_failure_recovery.v1",
        "automatic_failure_recovery_id": "recovery_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-156",
        "next_required_pr": "PR-ATLAS-SCALE-157",
        "status": status,
        "blocking_reasons": [] if status == "ready" else ["blocked_for_test"],
        "backend_authoritative": True,
        "reviewer": "atlas",
        "candidate_promotion_gate_path": str(data_root / "atlas" / "promotion" / "manifest.json"),
        "candidate_promotion_schema_version": "atlas.self_improvement_candidate_promotion_gate.v1",
        "candidate_promotion_track_pr": "PR-ATLAS-SCALE-155",
        "candidate_promotion_next_required_pr": "PR-ATLAS-SCALE-156",
        "candidate_root": str(data_root / "candidate"),
        "target_repo": str(data_root / "stable"),
        "stable_checkpoint_ref": "atlas/stable/checkpoint.json",
        "release_pointer_path": str(data_root / "releases" / "current_release.json"),
        "rollback_pointer_path": str(data_root / "releases" / "rollback_release.json"),
        "recovery_manifest_path": str(data_root / "checkpoint_store" / "recovery_manifest.json"),
        "recovery_manifest_schema_version": "atlas.recovery_supervisor_manifest.v1",
        "recovery_manifest_track_pr": "PR-ATLAS-SCALE-148",
        "recovery_manifest_next_required_pr": "PR-ATLAS-SCALE-149",
        "external_supervisor_required": True,
        "application_runtime_independent": True,
        "target_runtime_imports_forbidden": True,
        "web_runtime_imports_forbidden": True,
        "model_provider_imports_forbidden": True,
        "bounded_recovery": True,
        "recovery_strategy": "rollback_release_pointer",
        "max_recovery_attempts": 2,
        "recovery_evidence_refs": ["atlas/recovery/recovery-plan.json"] if status == "ready" else [],
        "automatic_failure_recovery_enabled": status == "ready",
        "automatic_failure_recovery_ready": status == "ready",
        "rollback_release_pointer_plan_ready": status == "ready",
        "manual_operation_required": True,
        "approval_required": True,
        "confirmation_text_required": "PREPARE AUTOMATIC FAILURE RECOVERY",
        "recovery_execution_enabled": False,
        "recovery_execution_performed": False,
        "restore_execution_enabled": False,
        "restore_performed": False,
        "pointer_switch_execution_enabled": False,
        "pointer_switched": False,
        "file_copy_execution_enabled": False,
        "file_copied": False,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "verification_execution_enabled": False,
        "verification_execution_performed": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "promotion_performed": False,
        "release_pointer_switch_performed": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "llm_recovery_enabled": False,
    }
    validate_automatic_failure_recovery_plan(payload)
    path = data_root / "atlas" / "automatic_failure_recovery" / "recovery_1" / "manifest.json"
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


def test_autonomous_loop_execution_v1_authorizes_bounded_session_without_stable_mutation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    profile_path = _safety_profile(data_root)
    recovery_path = _recovery_plan(data_root)

    session = create_autonomous_loop_execution_v1(
        automation_safety_profile_path=profile_path,
        automatic_failure_recovery_plan_path=recovery_path,
        data_root=data_root,
        loop_goal="continue Atlas SCALE roadmap through the next gated candidate step",
        max_iterations=3,
        allowed_loop_actions=[
            "read_backend_state",
            "select_next_candidate_step",
            "prepare_candidate_patch",
            "request_verification_gate",
            "request_recovery_plan",
            "stop_on_gate_failure",
            "record_progress_report",
        ],
        **_approved_kwargs(),
    )

    assert session["status"] == "ready"
    assert session["track_pr"] == "PR-ATLAS-SCALE-157"
    assert session["next_required_pr"] == "PR-ATLAS-SCALE-158"
    assert session["runtime_level"] == "level_5_autonomous_loop_execution_v1"
    assert session["runtime_transition_authorized"] is True
    assert session["autonomous_execution_enabled"] is True
    assert session["autonomous_loop_execution_enabled"] is True
    assert session["autonomous_loop_execution_v1_enabled"] is True
    assert session["max_iterations"] == 3
    assert session["bounded_loop_execution"] is True
    assert session["stop_on_failure"] is True
    assert session["recovery_plan_required_before_each_iteration"] is True
    assert session["backend_authoritative"] is True
    assert session["command_execution_enabled"] is False
    assert session["stable_runtime_mutation_enabled"] is False
    assert session["direct_merge_enabled"] is False
    assert session["remote_git_push_enabled"] is False
    assert session["self_apply_enabled"] is False
    assert session["vue_authoritative"] is False
    assert session["execute_all_enabled"] is False


def test_autonomous_loop_execution_v1_requires_autonomous_safety_profile(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    profile_path = _safety_profile(data_root, profile="supervised_bounded_auto")
    recovery_path = _recovery_plan(data_root)

    session = create_autonomous_loop_execution_v1(
        automation_safety_profile_path=profile_path,
        automatic_failure_recovery_plan_path=recovery_path,
        data_root=data_root,
        loop_goal="continue Atlas",
        **_approved_kwargs(),
    )

    assert session["status"] == "blocked"
    assert "autonomous_dev_agent_profile_required" in session["blocking_reasons"]
    assert "autonomous_loop_capability_required" in session["blocking_reasons"]
    assert session["runtime_level"] == "level_4_self_improvement_platform"
    assert session["autonomous_execution_enabled"] is False


def test_autonomous_loop_execution_v1_requires_ready_recovery_plan(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    profile_path = _safety_profile(data_root)
    recovery_path = _recovery_plan(data_root, status="blocked")

    session = create_autonomous_loop_execution_v1(
        automation_safety_profile_path=profile_path,
        automatic_failure_recovery_plan_path=recovery_path,
        data_root=data_root,
        loop_goal="continue Atlas",
        **_approved_kwargs(),
    )

    assert session["status"] == "blocked"
    assert "ready_automatic_failure_recovery_required" in session["blocking_reasons"]
    assert "automatic_failure_recovery_ready_required" in session["blocking_reasons"]
    assert session["autonomous_loop_execution_enabled"] is False


def test_autonomous_loop_execution_v1_blocks_unbounded_or_unsafe_actions(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    profile_path = _safety_profile(data_root)
    recovery_path = _recovery_plan(data_root)

    session = create_autonomous_loop_execution_v1(
        automation_safety_profile_path=profile_path,
        automatic_failure_recovery_plan_path=recovery_path,
        data_root=data_root,
        loop_goal="continue Atlas",
        allowed_loop_actions=["execute_shell"],
        max_iterations=4,
        stop_on_failure=False,
        **_approved_kwargs(),
    )

    assert session["status"] == "blocked"
    assert "loop_action_not_allowed" in session["blocking_reasons"]
    assert "max_iterations_must_be_1_to_3" in session["blocking_reasons"]
    assert "stop_on_failure_required" in session["blocking_reasons"]
    assert session["allowed_loop_actions"] == []


def test_validate_autonomous_loop_execution_v1_rejects_authority_escalation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    profile_path = _safety_profile(data_root)
    recovery_path = _recovery_plan(data_root)
    session = create_autonomous_loop_execution_v1(
        automation_safety_profile_path=profile_path,
        automatic_failure_recovery_plan_path=recovery_path,
        data_root=data_root,
        loop_goal="continue Atlas",
        **_approved_kwargs(),
    )
    session["direct_merge_enabled"] = True

    with pytest.raises(ValueError, match="invariant_violation:direct_merge_enabled"):
        validate_autonomous_loop_execution_v1(session)


def test_autonomous_loop_execution_v1_source_has_no_process_or_network_dependency() -> None:
    text = Path("app/atlas/autonomous_loop_execution_v1.py").read_text(encoding="utf-8")
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
