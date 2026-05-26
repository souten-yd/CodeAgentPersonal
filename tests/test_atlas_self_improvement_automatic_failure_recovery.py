import json
from pathlib import Path

import pytest

from app.atlas.self_improvement_automatic_failure_recovery import (
    REQUIRED_CONFIRMATION_TEXT,
    create_automatic_failure_recovery_plan,
    validate_automatic_failure_recovery_plan,
)
from app.atlas.self_improvement_candidate_promotion_gate import validate_self_improvement_candidate_promotion_gate
from recovery.recover import build_recovery_manifest, write_recovery_manifest


def _promotion_gate(tmp_path: Path, data_root: Path, *, status: str = "ready") -> Path:
    candidate_root = tmp_path / "candidate_repo"
    stable_root = tmp_path / "stable_repo"
    candidate_root.mkdir(parents=True, exist_ok=True)
    stable_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "atlas.self_improvement_candidate_promotion_gate.v1",
        "promotion_gate_id": "candidate_promote_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-155",
        "next_required_pr": "PR-ATLAS-SCALE-156",
        "status": status,
        "blocking_reasons": [] if status == "ready" else ["blocked_for_test"],
        "backend_authoritative": True,
        "reviewer": "atlas",
        "candidate_verification_gate_path": str(data_root / "atlas" / "verify.json"),
        "candidate_verification_schema_version": "atlas.self_improvement_candidate_verification_gate.v1",
        "candidate_verification_track_pr": "PR-ATLAS-SCALE-154",
        "candidate_verification_next_required_pr": "PR-ATLAS-SCALE-155",
        "candidate_root": str(candidate_root),
        "target_repo": str(stable_root),
        "changed_files": ["app/atlas/a.txt"] if status == "ready" else [],
        "verification_evidence_refs": ["atlas/candidate_verification/report.json"] if status == "ready" else [],
        "stable_checkpoint_ref": "atlas/stable/checkpoint.json",
        "recovery_manifest_ref": "atlas/recovery/manifest.json",
        "release_pointer_path": str(data_root / "releases" / "current_release.json"),
        "rollback_pointer_path": str(data_root / "releases" / "rollback_release.json"),
        "candidate_promotion_gate_enabled": status == "ready",
        "candidate_promotion_ready": status == "ready",
        "release_pointer_switch_ready": status == "ready",
        "rollback_ready_pointer_required": True,
        "manual_only": True,
        "approval_required": True,
        "confirmation_text_required": "PREPARE CANDIDATE PROMOTION GATE",
        "release_pointer_switch_performed": False,
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "verification_execution_enabled": False,
        "verification_execution_performed": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "promotion_performed": False,
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
    }
    validate_self_improvement_candidate_promotion_gate(payload)
    path = data_root / "atlas" / "self_improvement_candidate_promotion_gates" / "candidate_promote_1" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _recovery_manifest(data_root: Path) -> Path:
    store = data_root / "checkpoint_store"
    manifest = build_recovery_manifest(
        checkpoint_store=store,
        release_pointer_path=store / "current_release.json",
        recovery_reports_dir=store / "reports",
        stable_release_id="stable_001",
        allowed_actions=["inspect", "validate_pointer", "plan_pointer_switch", "record_report"],
    )
    return write_recovery_manifest(manifest=manifest, destination=store / "recovery_manifest.json")


def _approved_kwargs() -> dict[str, object]:
    return {
        "strict_gate_approved": True,
        "confirmation_token_present": True,
        "confirmation_text": REQUIRED_CONFIRMATION_TEXT,
        "approval_status": "approved",
        "explicit_decision": "approve",
    }


def test_automatic_failure_recovery_plan_ready_without_execution(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    promotion_path = _promotion_gate(tmp_path, data_root)
    recovery_path = _recovery_manifest(data_root)

    plan = create_automatic_failure_recovery_plan(
        candidate_promotion_gate_path=promotion_path,
        recovery_manifest_path=recovery_path,
        data_root=data_root,
        recovery_strategy="rollback_release_pointer",
        max_recovery_attempts=2,
        recovery_evidence_refs=["atlas/recovery/recovery-plan.json"],
        **_approved_kwargs(),
    )

    assert plan["status"] == "ready"
    assert plan["track_pr"] == "PR-ATLAS-SCALE-156"
    assert plan["next_required_pr"] == "PR-ATLAS-SCALE-157"
    assert plan["automatic_failure_recovery_enabled"] is True
    assert plan["automatic_failure_recovery_ready"] is True
    assert plan["rollback_release_pointer_plan_ready"] is True
    assert plan["external_supervisor_required"] is True
    assert plan["application_runtime_independent"] is True
    assert plan["bounded_recovery"] is True
    assert plan["max_recovery_attempts"] == 2
    assert plan["recovery_evidence_refs"] == ["atlas/recovery/recovery-plan.json"]
    assert plan["recovery_execution_enabled"] is False
    assert plan["recovery_execution_performed"] is False
    assert plan["pointer_switch_execution_enabled"] is False
    assert plan["pointer_switched"] is False
    assert plan["release_pointer_switch_performed"] is False
    assert plan["stable_runtime_mutation_enabled"] is False
    assert plan["direct_merge_enabled"] is False
    assert plan["remote_git_push_enabled"] is False
    assert plan["self_apply_enabled"] is False
    assert plan["vue_authoritative"] is False
    assert plan["llm_recovery_enabled"] is False


def test_automatic_failure_recovery_requires_ready_promotion_gate(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    promotion_path = _promotion_gate(tmp_path, data_root, status="blocked")
    recovery_path = _recovery_manifest(data_root)

    plan = create_automatic_failure_recovery_plan(
        candidate_promotion_gate_path=promotion_path,
        recovery_manifest_path=recovery_path,
        data_root=data_root,
        recovery_evidence_refs=["atlas/recovery/recovery-plan.json"],
        **_approved_kwargs(),
    )

    assert plan["status"] == "blocked"
    assert "ready_candidate_promotion_required" in plan["blocking_reasons"]
    assert "candidate_promotion_ready_required" in plan["blocking_reasons"]
    assert "release_pointer_switch_ready_required" in plan["blocking_reasons"]
    assert plan["automatic_failure_recovery_enabled"] is False
    assert plan["rollback_release_pointer_plan_ready"] is False


def test_automatic_failure_recovery_rejects_unsafe_strategy_attempts_and_refs(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    promotion_path = _promotion_gate(tmp_path, data_root)
    recovery_path = _recovery_manifest(data_root)

    with pytest.raises(ValueError, match="recovery_strategy|max_recovery_attempts"):
        create_automatic_failure_recovery_plan(
            candidate_promotion_gate_path=promotion_path,
            recovery_manifest_path=recovery_path,
            data_root=data_root,
            recovery_strategy="execute_shell_recovery",
            max_recovery_attempts=4,
            recovery_evidence_refs=["../outside.json"],
            **_approved_kwargs(),
        )


def test_validate_automatic_failure_recovery_rejects_execution_escalation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    promotion_path = _promotion_gate(tmp_path, data_root)
    recovery_path = _recovery_manifest(data_root)
    plan = create_automatic_failure_recovery_plan(
        candidate_promotion_gate_path=promotion_path,
        recovery_manifest_path=recovery_path,
        data_root=data_root,
        recovery_evidence_refs=["atlas/recovery/recovery-plan.json"],
        **_approved_kwargs(),
    )
    plan["pointer_switch_execution_enabled"] = True

    with pytest.raises(ValueError, match="invariant_violation:pointer_switch_execution_enabled"):
        validate_automatic_failure_recovery_plan(plan)


def test_automatic_failure_recovery_source_has_no_runtime_or_process_execution_dependency() -> None:
    text = Path("app/atlas/self_improvement_automatic_failure_recovery.py").read_text(encoding="utf-8")
    forbidden = [
        "subprocess",
        "os.system",
        "requests",
        "from fastapi",
        "import fastapi",
        "uvicorn",
        "git push",
        "git worktree",
        "safe_apply",
        "self_apply_to_stable_runtime",
    ]
    for needle in forbidden:
        assert needle not in text
