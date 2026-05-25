from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER_PLAN = ROOT / "docs" / "atlas_scale_master_roadmap.md"
POLICY = ROOT / "docs" / "atlas_autonomous_execution_readiness_policy.md"
PHASE_MANIFEST = ROOT / "docs" / "atlas_automation_phase_manifest.json"
UI_MANIFEST = ROOT / "web" / "atlas_ui_surface_manifest.json"
DELETED_DUPLICATE_DOCS = [
    ROOT / "docs" / "atlas_development_handoff.md",
    ROOT / "docs" / "atlas_thinui_readiness.md",
    ROOT / "docs" / "atlas_vue_migration_plan.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(_read(path))


def validate() -> None:
    master = _read(MASTER_PLAN)
    policy = _read(POLICY)
    phase = _load_json(PHASE_MANIFEST)
    ui_manifest = _load_json(UI_MANIFEST)

    assert phase["canonical_human_plan"] == "docs/atlas_scale_master_roadmap.md"
    assert phase["canonical_safety_policy"] == "docs/atlas_autonomous_execution_readiness_policy.md"
    assert phase["completed_automation_pr"] == "PR-ATLAS-SCALE-125"
    assert phase["current_automation_track"] == "PR-ATLAS-SCALE-126"
    assert phase["next_automation_track"] == "PR-ATLAS-SCALE-126"
    assert phase["completed_phase"] == "readiness_metadata_review"
    assert phase["automation_phase"] == "level_1_advancement_preparation"
    assert phase["current_level"] == "level_0_manual_only"
    assert phase["target_level"] == "level_1_guarded_single_step"
    assert phase["next_level_advancement_pr"] == "PR-ATLAS-SCALE-127"
    assert phase["final_goal"] == "fully_autonomous_code_agent"
    assert phase["self_improvement_goal"] == "self_improving_codeagentpersonal_kasanecore"
    assert phase["local_only_readiness_metadata_phase_complete"] is True
    assert phase["backend_workflow_state_authoritative"] is True
    assert phase["vue_source_of_truth"] is False
    assert phase["vue_execution_capability"] == "none"
    assert phase["level1_execution_enabled"] is False
    assert phase["autonomous_execution_enabled"] is False

    assert ui_manifest["final_goal"] == phase["final_goal"]
    assert ui_manifest["self_improvement_scope"] == phase["self_improvement_goal"]
    assert ui_manifest["level1_next_pr_must_not_enable_execution"] is True
    assert ui_manifest["vue_next_dry_run_result_viewer_checkpoint"] == "PR-ATLAS-SCALE-120"
    assert ui_manifest["vue_next_dry_run_result_viewer_enabled"] is True
    assert ui_manifest["vue_next_dry_run_result_viewer_display_only"] is True
    assert ui_manifest["vue_next_dry_run_result_viewer_backend_authoritative"] is True
    assert ui_manifest["vue_next_dry_run_result_viewer_starts_dry_run"] is False
    assert ui_manifest["vue_next_dry_run_result_viewer_captures_artifact"] is False
    assert ui_manifest["vue_next_dry_run_result_viewer_execution_enabled"] is False
    assert ui_manifest["vue_next_dry_run_result_viewer_mutation_enabled"] is False

    for path in DELETED_DUPLICATE_DOCS:
        assert not path.exists(), f"duplicate planning doc must stay deleted: {path}"

    for token in [
        "PR-ATLAS-SCALE-116",
        "PR-ATLAS-SCALE-117",
        "PR-ATLAS-SCALE-118",
        "PR-ATLAS-SCALE-119",
        "PR-ATLAS-SCALE-120",
        "PR-ATLAS-SCALE-121",
        "PR-ATLAS-SCALE-122",
        "PR-ATLAS-SCALE-123",
        "Level-1 Advancement Preparation",
        "PR-B is allowed only when",
        "must not add another local-only diff label/bookmark/annotation UX",
        "fully_autonomous_code_agent",
        "self_improving_codeagentpersonal_kasanecore",
    ]:
        assert token in master, token

    for token in [
        "Readiness Metadata Review Phase",
        "Level 1: Guarded single-step automation",
        "Level 4: Self-improvement candidate",
        "Anti-drift",
        "PR-B",
    ]:
        assert token in policy, token

    assert "Current automation track PR:\n- PR-ATLAS-SCALE-94" not in master
    assert "Next automation track PR:\n- PR-ATLAS-SCALE-94" not in master
    assert "next PR may add local-only diff label conflict export" not in master
    assert "next PR may add local-only diff label conflict export" not in policy

    planned = {item["pr"]: item for item in phase["planned_prs"]}
    for pr in [f"PR-ATLAS-SCALE-{i}" for i in range(113, 147)]:
        assert pr in planned, f"missing planned PR: {pr}"
        assert pr in master, f"master plan missing {pr}"

    assert planned["PR-ATLAS-SCALE-114"]["outcome"] == "advisory readiness rollup and gate evidence summary"
    assert planned["PR-ATLAS-SCALE-127"]["runtime_change_allowed"] is True
    assert planned["PR-ATLAS-SCALE-146"]["runtime_change_allowed"] is True


if __name__ == "__main__":
    validate()
    print("Atlas automation plan contract OK")
