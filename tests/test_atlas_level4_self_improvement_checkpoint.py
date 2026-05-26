import json
from pathlib import Path

import pytest

from app.atlas.level4_self_improvement_checkpoint import (
    REQUIRED_CONFIRMATION_TEXT,
    create_level4_self_improvement_checkpoint,
    load_level4_self_improvement_checkpoint,
    validate_level4_self_improvement_checkpoint,
    write_level4_self_improvement_checkpoint,
)


def _write_level3_candidate(tmp_path: Path, *, overrides: dict[str, object] | None = None) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    candidate_dir = data_root / "atlas" / "level3_autonomous_loop_candidates" / "candidate_1"
    candidate_dir.mkdir(parents=True)
    candidate: dict[str, object] = {
        "schema_version": "atlas.level3_autonomous_loop_candidate.v1",
        "candidate_id": "candidate_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "transition_pr": "PR-ATLAS-SCALE-139",
        "next_required_pr": "PR-ATLAS-SCALE-140",
        "previous_runtime_level": "level_2_guarded_bounded_loop",
        "runtime_level": "level_3_autonomous_implementation_loop_candidate",
        "target_runtime_level": "level_3_autonomous_implementation_loop_candidate",
        "candidate_authorized": True,
        "candidate_blocked": False,
        "blocking_reasons": [],
        "level2_checkpoint_path": str(data_root / "level2.json"),
        "data_root": str(data_root),
        "level3_autonomous_loop_candidate_enabled": True,
        "autonomous_loop_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "backend_authoritative": True,
        "draft_pr_only": True,
        "human_approval_required_for_apply": True,
        "human_approval_required_for_retry": True,
        "dry_run_required_before_apply": True,
        "stop_gate_required": True,
        "artifact_capture_required": True,
        "verification_allowlist_required": True,
        "max_iterations": 1,
        "max_retries": 0,
        "max_changed_files": 1,
        "max_runtime_minutes": 20,
        "max_risk_level": "low",
        "verification_commands": ["pytest", "atlas_smoke"],
        "allowed_candidate_actions": ["request_human_approval"],
        "forbidden_candidate_actions": ["direct_merge"],
        "execution_performed": False,
        "mutation_performed": False,
        "verification_performed": False,
        "retry_performed": False,
        "rollback_performed": False,
        "restore_performed": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    if overrides:
        candidate.update(overrides)
    path = candidate_dir / "manifest.json"
    path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    return data_root, path


def _write_draft_pr_creation(data_root: Path, *, overrides: dict[str, object] | None = None) -> Path:
    creation_dir = data_root / "atlas" / "self_improvement_draft_prs" / "creation_1"
    creation_dir.mkdir(parents=True)
    result: dict[str, object] = {
        "schema_version": "atlas.self_improvement_draft_pr_creation.v1",
        "creation_id": "creation_1",
        "track_pr": "PR-ATLAS-SCALE-145",
        "next_required_pr": "PR-ATLAS-SCALE-146",
        "apply_id": "apply_1",
        "transaction_id": "transaction_1",
        "status": "created",
        "blocked_reasons": [],
        "base_ref": "main",
        "head_branch": "codex/atlas-self-improvement-1",
        "changed_files": ["app/atlas/example.py"],
        "result_path": str(creation_dir / "manifest.json"),
        "dry_run": False,
        "draft_pr_title": "Atlas self-improvement draft PR",
        "draft_pr_body": "body",
        "single_action": True,
        "manual_only": True,
        "approval_required": True,
        "confirmation_text_required": "CREATE SELF IMPROVEMENT DRAFT PR",
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "execution_performed": False,
        "patch_generated": False,
        "automatic_pr_creation_enabled": False,
        "draft_pr_created": True,
        "draft_pr_updated": False,
        "verification_result_fabricated": False,
        "branch_created": False,
        "created_at": "2026-05-26T00:00:00+00:00",
        "draft_pr_number": 1000,
        "draft_pr_url": "https://github.com/souten-yd/KasaneCore/pull/1000",
        "draft_pr_api_url": "https://api.github.com/repos/souten-yd/KasaneCore/pulls/1000",
        "draft": True,
    }
    if overrides:
        result.update(overrides)
    path = creation_dir / "manifest.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return path


def test_create_level4_self_improvement_checkpoint_authorizes_with_all_gates(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(tmp_path)
    draft_pr_path = _write_draft_pr_creation(data_root)

    checkpoint = create_level4_self_improvement_checkpoint(
        level3_candidate_path=candidate_path,
        self_improvement_draft_pr_path=draft_pr_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        confirmation_token_present=True,
        confirmation_text=REQUIRED_CONFIRMATION_TEXT,
        strict_self_improvement_gates_ready=True,
    )

    assert checkpoint["transition_authorized"] is True
    assert checkpoint["runtime_level"] == "level_4_self_improvement_platform"
    assert checkpoint["level4_self_improvement_checkpoint_enabled"] is True
    assert checkpoint["self_improvement_platform_enabled"] is True
    assert checkpoint["draft_pr_only"] is True
    assert checkpoint["direct_merge_enabled"] is False
    assert checkpoint["stable_runtime_mutation_enabled"] is False
    assert checkpoint["self_modification_enabled"] is False
    assert checkpoint["self_apply_enabled"] is False
    assert checkpoint["remote_git_push_enabled"] is False
    assert checkpoint["vue_authoritative"] is False
    assert checkpoint["evidence_chain"]["draft_pr_number"] == 1000


def test_create_level4_self_improvement_checkpoint_blocks_without_human_approval(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(tmp_path)
    draft_pr_path = _write_draft_pr_creation(data_root)

    checkpoint = create_level4_self_improvement_checkpoint(
        level3_candidate_path=candidate_path,
        self_improvement_draft_pr_path=draft_pr_path,
        data_root=data_root,
    )

    assert checkpoint["transition_authorized"] is False
    assert checkpoint["runtime_level"] == "level_3_autonomous_implementation_loop_candidate"
    assert checkpoint["level4_self_improvement_checkpoint_enabled"] is False
    assert "explicit_human_approval_required" in checkpoint["blocking_reasons"]
    assert "confirmation_token_required" in checkpoint["blocking_reasons"]
    assert "strict_self_improvement_gates_required" in checkpoint["blocking_reasons"]


def test_create_level4_self_improvement_checkpoint_blocks_unapproved_level3_candidate(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(
        tmp_path,
        overrides={
            "candidate_authorized": False,
            "candidate_blocked": True,
            "runtime_level": "level_2_guarded_bounded_loop",
            "level3_autonomous_loop_candidate_enabled": False,
            "blocking_reasons": ["fixture_blocked"],
        },
    )
    draft_pr_path = _write_draft_pr_creation(data_root)

    checkpoint = create_level4_self_improvement_checkpoint(
        level3_candidate_path=candidate_path,
        self_improvement_draft_pr_path=draft_pr_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        confirmation_token_present=True,
        confirmation_text=REQUIRED_CONFIRMATION_TEXT,
        strict_self_improvement_gates_ready=True,
    )

    assert checkpoint["transition_authorized"] is False
    assert "level3_candidate_authorization_required" in checkpoint["blocking_reasons"]
    assert "level3_runtime_level_required" in checkpoint["blocking_reasons"]
    assert "level3_candidate_enabled_required" in checkpoint["blocking_reasons"]


def test_create_level4_self_improvement_checkpoint_blocks_missing_created_draft_pr(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(tmp_path)
    draft_pr_path = _write_draft_pr_creation(
        data_root,
        overrides={
            "status": "blocked",
            "blocked_reasons": ["fixture_blocked"],
            "changed_files": [],
            "draft_pr_created": False,
            "draft_pr_number": None,
            "draft_pr_url": "",
            "draft_pr_api_url": "",
            "draft": False,
        },
    )

    checkpoint = create_level4_self_improvement_checkpoint(
        level3_candidate_path=candidate_path,
        self_improvement_draft_pr_path=draft_pr_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        confirmation_token_present=True,
        confirmation_text=REQUIRED_CONFIRMATION_TEXT,
        strict_self_improvement_gates_ready=True,
    )

    assert checkpoint["transition_authorized"] is False
    assert "created_self_improvement_draft_pr_required" in checkpoint["blocking_reasons"]
    assert "draft_pr_must_remain_draft" in checkpoint["blocking_reasons"]
    assert "single_changed_file_required" in checkpoint["blocking_reasons"]


def test_validate_level4_self_improvement_checkpoint_rejects_forbidden_capability() -> None:
    checkpoint = {
        "schema_version": "atlas.level4_self_improvement_checkpoint.v1",
        "transition_pr": "PR-ATLAS-SCALE-146",
        "next_required_pr": "PR-ATLAS-SCALE-147",
        "previous_runtime_level": "level_3_autonomous_implementation_loop_candidate",
        "runtime_level": "level_4_self_improvement_platform",
        "target_runtime_level": "level_4_self_improvement_platform",
        "transition_authorized": True,
        "transition_blocked": False,
        "blocking_reasons": [],
        "level4_self_improvement_checkpoint_enabled": True,
        "self_improvement_platform_enabled": True,
        "strict_self_improvement_gates_ready": True,
        "candidate_workspace_required": True,
        "draft_pr_only": True,
        "direct_merge_forbidden": True,
        "stable_runtime_mutation_forbidden": True,
        "human_approval_required_for_self_improvement": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "direct_merge_enabled": True,
        "remote_git_push_enabled": False,
        "stable_runtime_mutation_enabled": False,
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
        "evidence_chain": {},
    }

    with pytest.raises(ValueError, match="direct_merge_enabled"):
        validate_level4_self_improvement_checkpoint(checkpoint)


def test_write_and_load_level4_self_improvement_checkpoint(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(tmp_path)
    draft_pr_path = _write_draft_pr_creation(data_root)
    checkpoint = create_level4_self_improvement_checkpoint(
        level3_candidate_path=candidate_path,
        self_improvement_draft_pr_path=draft_pr_path,
        data_root=data_root,
        approval_status="approved",
        explicit_decision="approve",
        confirmation_token_present=True,
        confirmation_text=REQUIRED_CONFIRMATION_TEXT,
        strict_self_improvement_gates_ready=True,
    )

    path = write_level4_self_improvement_checkpoint(data_root=data_root, checkpoint=checkpoint)
    loaded = load_level4_self_improvement_checkpoint(manifest_path=path, data_root=data_root)

    assert loaded["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert loaded["runtime_level"] == "level_4_self_improvement_platform"


def test_no_network_or_process_execution_in_level4_checkpoint_source() -> None:
    text = Path("app/atlas/level4_self_improvement_checkpoint.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
