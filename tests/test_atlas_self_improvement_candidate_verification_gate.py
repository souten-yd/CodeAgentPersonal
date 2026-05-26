import json
from pathlib import Path

import pytest

from app.atlas.self_improvement_candidate_apply import validate_self_improvement_candidate_apply
from app.atlas.self_improvement_candidate_verification_gate import (
    create_self_improvement_candidate_verification_gate,
    validate_self_improvement_candidate_verification_gate,
)


def _candidate_apply_result(
    tmp_path: Path,
    data_root: Path,
    *,
    status: str = "applied",
    candidate_apply_performed: bool = True,
    candidate_workspace_mutation_performed: bool = True,
) -> Path:
    candidate_root = tmp_path / "candidate_repo"
    stable_root = tmp_path / "stable_repo"
    candidate_root.mkdir(parents=True, exist_ok=True)
    stable_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "atlas.self_improvement_candidate_apply.v1",
        "track_pr": "PR-ATLAS-SCALE-153",
        "next_required_pr": "PR-ATLAS-SCALE-154",
        "status": status,
        "blocking_reasons": [] if status != "blocked" else ["blocked_for_test"],
        "backend_authoritative": True,
        "candidate_workspace_plan_id": "candidate_plan_1",
        "candidate_root": str(candidate_root),
        "target_repo": str(stable_root),
        "changed_files": ["app/atlas/a.txt"] if status == "applied" else [],
        "candidate_apply_enabled": status in {"planned", "applied"},
        "candidate_apply_performed": candidate_apply_performed,
        "candidate_workspace_mutation_performed": candidate_workspace_mutation_performed,
        "inner_apply_status": status,
        "inner_apply_id": "apply_1",
        "inner_apply_result_path": str(data_root / "atlas" / "self_improvement_patch_applies" / "apply_1" / "manifest.json"),
        "dry_run": False,
        "single_action": True,
        "manual_only": True,
        "approval_required": True,
        "confirmation_text_required": "APPLY SELF IMPROVEMENT CANDIDATE PATCH",
        "stable_runtime_mutation_enabled": False,
        "stable_runtime_mutation_performed": False,
        "self_apply_enabled": False,
        "self_modification_enabled": False,
        "command_execution_enabled": False,
        "command_execution_performed": False,
        "verification_execution_enabled": False,
        "verification_performed": False,
        "promotion_enabled": False,
        "promotion_performed": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
    }
    validate_self_improvement_candidate_apply(payload)
    path = data_root / "atlas" / "self_improvement_candidate_applies" / "apply_1" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_candidate_verification_gate_records_allowlisted_plan_without_execution(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    apply_path = _candidate_apply_result(tmp_path, data_root)

    gate = create_self_improvement_candidate_verification_gate(
        candidate_apply_result_path=apply_path,
        proposed_commands=["pytest -q tests/test_atlas_self_improvement_candidate_verification_gate.py"],
        verification_evidence_refs=["atlas/candidate_verification/report.json"],
        data_root=data_root,
    )

    assert gate["status"] == "ready"
    assert gate["track_pr"] == "PR-ATLAS-SCALE-154"
    assert gate["next_required_pr"] == "PR-ATLAS-SCALE-155"
    assert gate["candidate_verification_gate_enabled"] is True
    assert gate["candidate_verification_ready"] is True
    assert gate["allowlisted_verification_only"] is True
    assert gate["no_promote_without_evidence"] is True
    assert gate["allowed_commands"] == ["pytest -q tests/test_atlas_self_improvement_candidate_verification_gate.py"]
    assert gate["blocked_commands"] == []
    assert gate["verification_evidence_refs"] == ["atlas/candidate_verification/report.json"]
    assert gate["command_execution_enabled"] is False
    assert gate["command_execution_performed"] is False
    assert gate["verification_execution_enabled"] is False
    assert gate["verification_execution_performed"] is False
    assert gate["verification_performed"] is False
    assert gate["verification_result_fabricated"] is False
    assert gate["candidate_promotion_enabled"] is False
    assert gate["promotion_enabled"] is False
    assert gate["stable_runtime_mutation_enabled"] is False
    assert gate["direct_merge_enabled"] is False
    assert gate["remote_git_push_enabled"] is False
    assert gate["vue_authoritative"] is False


def test_candidate_verification_gate_blocks_non_allowlisted_command(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    apply_path = _candidate_apply_result(tmp_path, data_root)

    gate = create_self_improvement_candidate_verification_gate(
        candidate_apply_result_path=apply_path,
        proposed_commands=["pytest", "git push origin main"],
        verification_evidence_refs=["atlas/candidate_verification/report.json"],
        data_root=data_root,
    )

    assert gate["status"] == "blocked"
    assert "only_allowlisted_candidate_verification_commands_allowed" in gate["blocking_reasons"]
    assert gate["candidate_verification_gate_enabled"] is False
    assert gate["candidate_verification_ready"] is False
    assert gate["allowed_commands"] == []
    assert gate["blocked_commands"] == ["pytest", "git push origin main"]
    assert gate["verification_execution_enabled"] is False


def test_candidate_verification_gate_requires_applied_candidate(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    apply_path = _candidate_apply_result(
        tmp_path,
        data_root,
        status="planned",
        candidate_apply_performed=False,
        candidate_workspace_mutation_performed=False,
    )

    gate = create_self_improvement_candidate_verification_gate(
        candidate_apply_result_path=apply_path,
        proposed_commands=["pytest -q tests/test_atlas_self_improvement_candidate_verification_gate.py"],
        verification_evidence_refs=["atlas/candidate_verification/report.json"],
        data_root=data_root,
    )

    assert gate["status"] == "blocked"
    assert "applied_candidate_required" in gate["blocking_reasons"]
    assert "candidate_apply_performed_required" in gate["blocking_reasons"]
    assert "candidate_workspace_mutation_required" in gate["blocking_reasons"]
    assert gate["changed_files"] == []


def test_candidate_verification_gate_requires_relative_evidence_ref(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    apply_path = _candidate_apply_result(tmp_path, data_root)

    gate = create_self_improvement_candidate_verification_gate(
        candidate_apply_result_path=apply_path,
        proposed_commands=["pytest -q tests/test_atlas_self_improvement_candidate_verification_gate.py"],
        verification_evidence_refs=["../outside/report.json"],
        data_root=data_root,
    )

    assert gate["status"] == "blocked"
    assert "verification_evidence_ref_must_be_relative" in gate["blocking_reasons"]
    assert "verification_evidence_refs_required" in gate["blocking_reasons"]


def test_validate_candidate_verification_gate_rejects_authority_escalation(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    apply_path = _candidate_apply_result(tmp_path, data_root)
    gate = create_self_improvement_candidate_verification_gate(
        candidate_apply_result_path=apply_path,
        proposed_commands=["pytest -q tests/test_atlas_self_improvement_candidate_verification_gate.py"],
        verification_evidence_refs=["atlas/candidate_verification/report.json"],
        data_root=data_root,
    )
    gate["candidate_promotion_enabled"] = True

    with pytest.raises(ValueError, match="invariant_violation:candidate_promotion_enabled"):
        validate_self_improvement_candidate_verification_gate(gate)


def test_candidate_verification_gate_source_has_no_runtime_or_process_execution_dependency() -> None:
    text = Path("app/atlas/self_improvement_candidate_verification_gate.py").read_text(encoding="utf-8")
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
