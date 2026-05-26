import json
from pathlib import Path

import pytest

from app.atlas.automation_safety_profile import (
    PROFILE_AUTONOMOUS_DEV_AGENT,
    PROFILE_GUARDED_SINGLE_ACTION,
    PROFILE_REVIEW_ONLY,
    PROFILE_SUPERVISED_BOUNDED_AUTO,
    SELF_SCOPE_ATLAS_NON_RUNTIME,
    SELF_SCOPE_NONE,
    create_automation_safety_profile,
    load_automation_safety_profile,
    validate_automation_safety_profile,
    write_automation_safety_profile,
)


def _write_level4_checkpoint(tmp_path: Path, *, overrides: dict[str, object] | None = None) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    checkpoint_dir = data_root / "atlas" / "level4_self_improvement_checkpoints" / "checkpoint_1"
    checkpoint_dir.mkdir(parents=True)
    checkpoint: dict[str, object] = {
        "schema_version": "atlas.level4_self_improvement_checkpoint.v1",
        "checkpoint_id": "checkpoint_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "transition_pr": "PR-ATLAS-SCALE-146",
        "next_required_pr": "PR-ATLAS-SCALE-147",
        "previous_runtime_level": "level_3_autonomous_implementation_loop_candidate",
        "runtime_level": "level_4_self_improvement_platform",
        "target_runtime_level": "level_4_self_improvement_platform",
        "transition_authorized": True,
        "transition_blocked": False,
        "blocking_reasons": [],
        "level3_candidate_path": str(data_root / "level3.json"),
        "self_improvement_draft_pr_path": str(data_root / "draft_pr.json"),
        "data_root": str(data_root),
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
        "direct_merge_enabled": False,
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
        "evidence_chain": {"draft_pr_number": 1000, "changed_files": ["app/atlas/example.py"]},
        "allowed_level4_actions": ["request_human_review"],
        "forbidden_level4_actions": ["direct_merge"],
    }
    if overrides:
        checkpoint.update(overrides)
    path = checkpoint_dir / "manifest.json"
    path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
    return data_root, path


def test_review_only_profile_is_active_and_non_mutating() -> None:
    profile = create_automation_safety_profile(profile=PROFILE_REVIEW_ONLY, explicit_profile_selection=True)

    assert profile["status"] == "active"
    assert profile["automation_safety_profile_framework_enabled"] is True
    assert profile["automation_safety_profile"] == PROFILE_REVIEW_ONLY
    assert profile["self_improvement_enabled"] is False
    assert profile["capabilities"]["allows_file_mutation"] is False
    assert profile["capabilities"]["allows_command_execution"] is False
    assert profile["direct_merge_enabled"] is False
    assert profile["remote_git_push_enabled"] is False
    assert profile["stable_runtime_mutation_enabled"] is False
    assert profile["vue_authoritative"] is False


def test_all_profiles_have_backend_owned_capability_metadata() -> None:
    profiles = [
        PROFILE_REVIEW_ONLY,
        PROFILE_GUARDED_SINGLE_ACTION,
        PROFILE_SUPERVISED_BOUNDED_AUTO,
        PROFILE_AUTONOMOUS_DEV_AGENT,
    ]

    created = [create_automation_safety_profile(profile=name, explicit_profile_selection=True) for name in profiles]

    assert [item["profile_rank"] for item in created] == [0, 1, 2, 3]
    assert created[0]["capabilities"]["allows_file_mutation"] is False
    assert created[1]["capabilities"]["requires_human_approval_for_mutation"] is True
    assert created[2]["capabilities"]["allows_draft_pr_creation"] is True
    assert created[3]["capabilities"]["allows_autonomous_loop_execution"] is True
    for item in created:
        assert item["backend_authoritative"] is True
        assert item["direct_merge_enabled"] is False
        assert item["self_modification_enabled"] is False
        assert item["execution_performed"] is False
        assert item["mutation_performed"] is False


def test_profile_blocks_without_explicit_selection() -> None:
    profile = create_automation_safety_profile(profile=PROFILE_REVIEW_ONLY)

    assert profile["status"] == "blocked"
    assert profile["automation_safety_profile_framework_enabled"] is False
    assert "explicit_profile_selection_required" in profile["blocking_reasons"]


def test_self_improvement_requires_level4_checkpoint_and_strict_gate(tmp_path: Path) -> None:
    data_root, checkpoint_path = _write_level4_checkpoint(tmp_path)

    profile = create_automation_safety_profile(
        profile=PROFILE_SUPERVISED_BOUNDED_AUTO,
        data_root=data_root,
        level4_checkpoint_path=checkpoint_path,
        self_improvement_enabled=True,
        self_improvement_scope=SELF_SCOPE_ATLAS_NON_RUNTIME,
        explicit_profile_selection=True,
        strict_gate_approved=True,
    )

    assert profile["status"] == "active"
    assert profile["self_improvement_enabled"] is True
    assert profile["requested_self_improvement_enabled"] is True
    assert profile["self_improvement_scope"] == SELF_SCOPE_ATLAS_NON_RUNTIME
    assert profile["level4_checkpoint_path"] == str(checkpoint_path.resolve())
    assert profile["direct_merge_enabled"] is False
    assert profile["stable_runtime_mutation_enabled"] is False


def test_self_improvement_blocks_low_profile_and_missing_checkpoint() -> None:
    profile = create_automation_safety_profile(
        profile=PROFILE_REVIEW_ONLY,
        self_improvement_enabled=True,
        self_improvement_scope=SELF_SCOPE_ATLAS_NON_RUNTIME,
        explicit_profile_selection=True,
    )

    assert profile["status"] == "blocked"
    assert profile["self_improvement_enabled"] is False
    assert "self_improvement_requires_supervised_or_higher_profile" in profile["blocking_reasons"]
    assert "strict_gate_approval_required_for_self_improvement" in profile["blocking_reasons"]
    assert "level4_checkpoint_required_for_self_improvement" in profile["blocking_reasons"]


def test_self_improvement_blocks_unapproved_level4_checkpoint(tmp_path: Path) -> None:
    data_root, checkpoint_path = _write_level4_checkpoint(
        tmp_path,
        overrides={
            "transition_authorized": False,
            "transition_blocked": True,
            "runtime_level": "level_3_autonomous_implementation_loop_candidate",
            "level4_self_improvement_checkpoint_enabled": False,
            "self_improvement_platform_enabled": False,
            "blocking_reasons": ["fixture_blocked"],
        },
    )

    profile = create_automation_safety_profile(
        profile=PROFILE_SUPERVISED_BOUNDED_AUTO,
        data_root=data_root,
        level4_checkpoint_path=checkpoint_path,
        self_improvement_enabled=True,
        self_improvement_scope=SELF_SCOPE_ATLAS_NON_RUNTIME,
        explicit_profile_selection=True,
        strict_gate_approved=True,
    )

    assert profile["status"] == "blocked"
    assert "level4_checkpoint_authorization_required" in profile["blocking_reasons"]
    assert "level4_runtime_level_required" in profile["blocking_reasons"]
    assert "level4_checkpoint_enabled_required" in profile["blocking_reasons"]


def test_validate_rejects_forbidden_direct_merge() -> None:
    profile = create_automation_safety_profile(profile=PROFILE_REVIEW_ONLY, explicit_profile_selection=True)
    profile["direct_merge_enabled"] = True

    with pytest.raises(ValueError, match="direct_merge_enabled"):
        validate_automation_safety_profile(profile)


def test_validate_rejects_scope_without_self_improvement() -> None:
    profile = create_automation_safety_profile(
        profile=PROFILE_REVIEW_ONLY,
        self_improvement_enabled=False,
        self_improvement_scope=SELF_SCOPE_NONE,
        explicit_profile_selection=True,
    )
    profile["self_improvement_scope"] = SELF_SCOPE_ATLAS_NON_RUNTIME

    with pytest.raises(ValueError, match="self_improvement_scope"):
        validate_automation_safety_profile(profile)


def test_write_and_load_automation_safety_profile(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    profile = create_automation_safety_profile(profile=PROFILE_GUARDED_SINGLE_ACTION, explicit_profile_selection=True)

    path = write_automation_safety_profile(data_root=data_root, profile=profile)
    loaded = load_automation_safety_profile(manifest_path=path, data_root=data_root)

    assert loaded["profile_id"] == profile["profile_id"]
    assert loaded["automation_safety_profile"] == PROFILE_GUARDED_SINGLE_ACTION


def test_no_network_or_process_execution_in_profile_source() -> None:
    text = Path("app/atlas/automation_safety_profile.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
