import json
from pathlib import Path

import pytest

from app.atlas.self_improvement_candidate_promotion_gate import (
    REQUIRED_CONFIRMATION_TEXT,
    create_self_improvement_candidate_promotion_gate,
    validate_self_improvement_candidate_promotion_gate,
)
from app.atlas.self_improvement_candidate_verification_gate import validate_self_improvement_candidate_verification_gate


def _verification_gate(tmp_path: Path, data_root: Path, *, status: str = "ready") -> Path:
    candidate_root = tmp_path / "candidate_repo"
    stable_root = tmp_path / "stable_repo"
    candidate_root.mkdir(parents=True, exist_ok=True)
    stable_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "atlas.self_improvement_candidate_verification_gate.v1",
        "gate_id": "candidate_verify_1",
        "track_pr": "PR-ATLAS-SCALE-154",
        "next_required_pr": "PR-ATLAS-SCALE-155",
        "status": status,
        "blocking_reasons": [] if status == "ready" else ["blocked_for_test"],
        "backend_authoritative": True,
        "candidate_apply_schema_version": "atlas.self_improvement_candidate_apply.v1",
        "candidate_apply_track_pr": "PR-ATLAS-SCALE-153",
        "candidate_apply_next_required_pr": "PR-ATLAS-SCALE-154",
        "candidate_root": str(candidate_root),
        "target_repo": str(stable_root),
        "changed_files": ["app/atlas/a.txt"] if status == "ready" else [],
        "proposed_commands": ["pytest -q tests/test_atlas_self_improvement_candidate_promotion_gate.py"],
        "command_results": [
            {
                "command": "pytest -q tests/test_atlas_self_improvement_candidate_promotion_gate.py",
                "allowed": True,
                "requires_human_approval": True,
            }
        ],
        "allowed_commands": ["pytest -q tests/test_atlas_self_improvement_candidate_promotion_gate.py"],
        "blocked_commands": [],
        "verification_evidence_refs": ["atlas/candidate_verification/report.json"] if status == "ready" else [],
        "candidate_verification_gate_enabled": status == "ready",
        "candidate_verification_ready": status == "ready",
        "allowlisted_verification_only": True,
        "no_promote_without_evidence": True,
        "manual_only": True,
        "approval_required": True,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "verification_execution_enabled": False,
        "verification_execution_performed": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "candidate_promotion_enabled": False,
        "promotion_enabled": False,
        "promotion_performed": False,
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
    }
    validate_self_improvement_candidate_verification_gate(payload)
    path = data_root / "atlas" / "self_improvement_candidate_verification_gates" / "candidate_verify_1" / "manifest.json"
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


def test_candidate_promotion_gate_prepares_pointer_switch_without_mutation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    verification_path = _verification_gate(tmp_path, data_root)

    gate = create_self_improvement_candidate_promotion_gate(
        candidate_verification_gate_path=verification_path,
        data_root=data_root,
        release_pointer_path=data_root / "releases" / "current_release.json",
        rollback_pointer_path=data_root / "releases" / "rollback_release.json",
        stable_checkpoint_ref="atlas/stable/checkpoint.json",
        recovery_manifest_ref="atlas/recovery/manifest.json",
        **_approved_kwargs(),
    )

    assert gate["status"] == "ready"
    assert gate["track_pr"] == "PR-ATLAS-SCALE-155"
    assert gate["next_required_pr"] == "PR-ATLAS-SCALE-156"
    assert gate["candidate_promotion_gate_enabled"] is True
    assert gate["candidate_promotion_ready"] is True
    assert gate["release_pointer_switch_ready"] is True
    assert gate["rollback_ready_pointer_required"] is True
    assert gate["changed_files"] == ["app/atlas/a.txt"]
    assert gate["verification_evidence_refs"] == ["atlas/candidate_verification/report.json"]
    assert gate["release_pointer_switch_performed"] is False
    assert gate["promotion_performed"] is False
    assert gate["stable_runtime_mutation_enabled"] is False
    assert gate["stable_runtime_mutation_performed"] is False
    assert gate["direct_merge_enabled"] is False
    assert gate["remote_git_push_enabled"] is False
    assert gate["self_apply_enabled"] is False
    assert gate["vue_authoritative"] is False


def test_candidate_promotion_gate_requires_ready_verification(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    verification_path = _verification_gate(tmp_path, data_root, status="blocked")

    gate = create_self_improvement_candidate_promotion_gate(
        candidate_verification_gate_path=verification_path,
        data_root=data_root,
        release_pointer_path=data_root / "releases" / "current_release.json",
        rollback_pointer_path=data_root / "releases" / "rollback_release.json",
        stable_checkpoint_ref="atlas/stable/checkpoint.json",
        recovery_manifest_ref="atlas/recovery/manifest.json",
        **_approved_kwargs(),
    )

    assert gate["status"] == "blocked"
    assert "ready_candidate_verification_required" in gate["blocking_reasons"]
    assert "candidate_verification_ready_required" in gate["blocking_reasons"]
    assert gate["candidate_promotion_gate_enabled"] is False
    assert gate["release_pointer_switch_ready"] is False


def test_candidate_promotion_gate_requires_rollback_pointer_and_confirmation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    verification_path = _verification_gate(tmp_path, data_root)
    kwargs = _approved_kwargs()
    kwargs["confirmation_text"] = "PROMOTE"

    gate = create_self_improvement_candidate_promotion_gate(
        candidate_verification_gate_path=verification_path,
        data_root=data_root,
        release_pointer_path=data_root / "releases" / "current_release.json",
        rollback_pointer_path=data_root / "releases" / "current_release.json",
        stable_checkpoint_ref="atlas/stable/checkpoint.json",
        recovery_manifest_ref="atlas/recovery/manifest.json",
        **kwargs,
    )

    assert gate["status"] == "blocked"
    assert "rollback_pointer_filename_required" in gate["blocking_reasons"]
    assert "release_and_rollback_pointer_must_differ" in gate["blocking_reasons"]
    assert "confirmation_text_mismatch" in gate["blocking_reasons"]


def test_validate_candidate_promotion_gate_rejects_mutation_escalation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    verification_path = _verification_gate(tmp_path, data_root)
    gate = create_self_improvement_candidate_promotion_gate(
        candidate_verification_gate_path=verification_path,
        data_root=data_root,
        release_pointer_path=data_root / "releases" / "current_release.json",
        rollback_pointer_path=data_root / "releases" / "rollback_release.json",
        stable_checkpoint_ref="atlas/stable/checkpoint.json",
        recovery_manifest_ref="atlas/recovery/manifest.json",
        **_approved_kwargs(),
    )
    gate["stable_runtime_mutation_enabled"] = True

    with pytest.raises(ValueError, match="invariant_violation:stable_runtime_mutation_enabled"):
        validate_self_improvement_candidate_promotion_gate(gate)


def test_candidate_promotion_gate_source_has_no_runtime_or_process_execution_dependency() -> None:
    text = Path("app/atlas/self_improvement_candidate_promotion_gate.py").read_text(encoding="utf-8")
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
