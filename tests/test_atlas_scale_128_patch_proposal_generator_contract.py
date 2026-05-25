import json
from pathlib import Path

import pytest

from app.atlas.level1_patch_proposal_generator import (
    SCHEMA_VERSION,
    create_level1_patch_proposal,
    load_level1_patch_proposal,
    validate_level1_patch_proposal,
    write_level1_patch_proposal,
)


def _proposal(project: Path, data_root: Path) -> dict:
    target = project / "app" / "atlas"
    target.mkdir(parents=True, exist_ok=True)
    (target / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
    return create_level1_patch_proposal(
        project_path=project,
        data_root=data_root,
        requirement="Add a guarded proposal artifact for the next Atlas patch step.",
        proposal_title="SCALE-128 patch proposal",
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        proposed_changes=[
            {
                "relative_path": "app/atlas/example.py",
                "change_type": "modify",
                "rationale": "Prepare metadata before creating a patch transaction.",
                "acceptance_criteria": "Proposal remains metadata only.",
                "risk_level": "low",
            }
        ],
    )


def test_scale_128_creates_metadata_only_patch_proposal(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    proposal = _proposal(project, data_root)

    assert proposal["schema_version"] == SCHEMA_VERSION
    assert proposal["proposal_pr"] == "PR-ATLAS-SCALE-128"
    assert proposal["next_required_pr"] == "PR-ATLAS-SCALE-129"
    assert proposal["runtime_level"] == "level_1_guarded_single_step"
    assert proposal["proposal_mode"] == "metadata_only_patch_proposal"
    assert proposal["proposal_generated"] is True
    assert proposal["patch_text_generated"] is False
    assert proposal["diff_generated"] is False
    assert proposal["patch_transaction_created"] is False
    assert proposal["patch_apply_enabled"] is False
    assert proposal["safe_apply_enabled"] is False
    assert proposal["automatic_patch_generation_enabled"] is False
    assert proposal["automatic_patch_apply_enabled"] is False
    assert proposal["automatic_safe_apply_enabled"] is False
    assert proposal["execution_enabled"] is False
    assert proposal["autonomous_execution_enabled"] is False
    assert proposal["remote_git_operations_enabled"] is False
    assert proposal["public_route_added"] is False
    assert proposal["vue_authoritative"] is False
    assert proposal["backend_authoritative"] is True
    assert proposal["manual_review_required"] is True
    assert proposal["target_file_count"] == 1
    assert proposal["valid_target_file_count"] == 1

    path = write_level1_patch_proposal(data_root=data_root, proposal=proposal)
    assert path.exists()
    assert path.is_relative_to(data_root)
    loaded = load_level1_patch_proposal(manifest_path=path, data_root=data_root)
    assert loaded["proposal_id"] == proposal["proposal_id"]


def test_scale_128_blocks_unsafe_paths_without_throwing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    proposal = create_level1_patch_proposal(
        project_path=project,
        data_root=data_root,
        requirement="Unsafe path should be review blocked.",
        proposed_changes=[{"relative_path": "../outside.py", "change_type": "modify"}],
    )

    assert proposal["proposal_status"] == "proposal_needs_review"
    assert proposal["valid_target_file_count"] == 0
    assert proposal["proposed_changes"][0]["path_valid"] is False
    assert "invalid_target_path_present" in proposal["warnings"]
    assert "path_traversal_forbidden" in proposal["proposed_changes"][0]["warnings"]
    assert proposal["patch_transaction_created"] is False


def test_scale_128_validation_rejects_forbidden_capabilities(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    proposal = _proposal(project, data_root)
    proposal["patch_apply_enabled"] = True
    with pytest.raises(ValueError, match="patch_apply_enabled"):
        validate_level1_patch_proposal(proposal)

    proposal = _proposal(project, data_root)
    proposal["diff_text"] = "diff --git a/x b/x"
    with pytest.raises(ValueError, match="forbidden_field:diff_text"):
        validate_level1_patch_proposal(proposal)


def test_scale_128_module_has_no_execution_or_mutation_tokens() -> None:
    source = Path("app/atlas/level1_patch_proposal_generator.py").read_text(encoding="utf-8")
    for token in [
        "subprocess",
        "os.system",
        "shell=True",
        "Popen",
        "check_output",
        "safe_apply(",
        "git push",
        "git pull",
        "git clone",
        "@router.post",
        "/api/atlas/level1/execute",
    ]:
        assert token not in source


def test_scale_128_manifest_and_plan_pointers_advance_to_patch_transaction_preview() -> None:
    phase = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
    ui = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    roadmap = Path("docs/atlas_scale_master_roadmap.md").read_text(encoding="utf-8")
    policy = Path("docs/atlas_autonomous_execution_readiness_policy.md").read_text(encoding="utf-8")
    status = Path("docs/atlas_autopilot_current_status.md").read_text(encoding="utf-8")

    assert phase["completed_automation_pr"] == "PR-ATLAS-SCALE-128"
    assert phase["current_automation_track"] == "PR-ATLAS-SCALE-129"
    assert phase["next_automation_track"] == "PR-ATLAS-SCALE-129"
    assert phase["current_level"] == "level_1_guarded_single_step"
    assert phase["level1_execution_enabled"] is True
    assert phase["autonomous_execution_enabled"] is False

    assert ui["level1_patch_proposal_generator_checkpoint"] == "PR-ATLAS-SCALE-128"
    assert ui["level1_patch_proposal_generator_next_required_pr"] == "PR-ATLAS-SCALE-129"
    assert ui["level1_patch_proposal_generator_patch_transaction_created"] is False
    assert ui["level1_patch_proposal_generator_patch_apply_enabled"] is False
    assert ui["level1_patch_proposal_generator_autonomous_execution_enabled"] is False

    assert "SCALE-128 completed: metadata-only patch proposal generator" in roadmap
    assert "PR-ATLAS-SCALE-128 adds metadata-only patch proposals" in policy
    assert "PR-ATLAS-SCALE-129: patch transaction preview" in status
