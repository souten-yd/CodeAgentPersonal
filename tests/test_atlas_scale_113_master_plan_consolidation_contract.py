from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER_PLAN = ROOT / "docs" / "atlas_scale_master_roadmap.md"
POLICY = ROOT / "docs" / "atlas_autonomous_execution_readiness_policy.md"
PHASE_MANIFEST = ROOT / "docs" / "atlas_automation_phase_manifest.json"
VALIDATOR = ROOT / "scripts" / "validate_atlas_automation_plan.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_scale_113_defines_single_canonical_master_plan() -> None:
    master = read(MASTER_PLAN)
    policy = read(POLICY)
    phase = json.loads(read(PHASE_MANIFEST))

    assert "single human-readable source of truth" in master
    assert phase["canonical_human_plan"] == "docs/atlas_scale_master_roadmap.md"
    assert phase["canonical_safety_policy"] == "docs/atlas_autonomous_execution_readiness_policy.md"
    assert "Do not duplicate active/current/next PR pointers" in policy
    assert "docs/atlas_automation_phase_manifest.json" in master
    assert "docs/atlas_scale_master_roadmap.md" in policy


def test_scale_113_preserves_final_goal_and_self_improvement_goal() -> None:
    phase = json.loads(read(PHASE_MANIFEST))
    master = read(MASTER_PLAN)
    policy = read(POLICY)

    assert phase["final_goal"] == "fully_autonomous_code_agent"
    assert phase["self_improvement_goal"] == "self_improving_codeagentpersonal_kasanecore"
    assert "Final goal: fully_autonomous_code_agent" in master
    assert "Self-improvement goal: self_improving_codeagentpersonal_kasanecore" in master
    assert "fully autonomous code agent" in policy
    assert "self-improving CodeAgentPersonal / KasaneCore platform" in policy


def test_scale_113_closes_local_only_metadata_phase_and_points_to_level1() -> None:
    phase = json.loads(read(PHASE_MANIFEST))
    master = read(MASTER_PLAN)

    assert phase["completed_phase"] == "readiness_metadata_review"
    assert phase["automation_phase"] == "level_1_advancement_preparation"
    assert phase["local_only_readiness_metadata_phase_complete"] is True
    assert phase["current_level"] == "level_0_manual_only"
    assert phase["target_level"] == "level_1_guarded_single_step"
    assert "SCALE-100 through SCALE-112 are complete" in master
    assert "SCALE-113 starts the Level-1 Advancement Preparation phase" in master
    assert "Next PRs must advance Level-1 readiness evidence" in master


def test_scale_113_pr_plan_is_explicit_and_allows_pr_b_repairs_only() -> None:
    phase = json.loads(read(PHASE_MANIFEST))
    planned = {item["pr"]: item for item in phase["planned_prs"]}
    master = read(MASTER_PLAN)

    assert "PR-ATLAS-SCALE-114" in planned
    assert planned["PR-ATLAS-SCALE-114"]["outcome"] == "advisory readiness rollup and gate evidence summary"
    assert planned["PR-ATLAS-SCALE-127"]["runtime_change_allowed"] is True
    assert planned["PR-ATLAS-SCALE-146"]["runtime_change_allowed"] is True
    assert phase["allowed_pr_b_policy"]["scope"] == "repair_only"
    assert phase["allowed_pr_b_policy"]["must_not_delay_level_1_advancement"] is True
    assert "PR-B is allowed only when" in master
    assert "must not introduce a new feature family" in master


def test_scale_113_duplicate_planning_docs_removed() -> None:
    phase = json.loads(read(PHASE_MANIFEST))
    for relative_path in phase["deleted_duplicate_planning_files"]:
        assert not (ROOT / relative_path).exists(), relative_path


def test_scale_113_validator_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Atlas automation plan contract OK" in result.stdout


def test_scale_113_forbids_known_drift_phrases() -> None:
    combined = read(MASTER_PLAN) + "\n" + read(POLICY)
    assert "next PR may add local-only diff label conflict export" not in combined
    assert "Current automation track PR:\n- PR-ATLAS-SCALE-94" not in combined
    assert "Next automation track PR:\n- PR-ATLAS-SCALE-94" not in combined
