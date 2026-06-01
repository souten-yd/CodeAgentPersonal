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


def _section(text: str, start_heading: str, end_heading: str | None = None) -> str:
    start = text.index(start_heading)
    if end_heading is None:
        return text[start:]
    end = text.index(end_heading, start + len(start_heading))
    return text[start:end]


def validate() -> None:
    master = _read(MASTER_PLAN)
    policy = _read(POLICY)
    phase = _load_json(PHASE_MANIFEST)
    ui_manifest = _load_json(UI_MANIFEST)

    assert phase["canonical_human_plan"] == "docs/atlas_scale_master_roadmap.md"
    assert phase["canonical_safety_policy"] == "docs/atlas_autonomous_execution_readiness_policy.md"
    assert phase["runtime_level_model"] == "profile_dependent"
    assert phase["current_level_semantics"] == "max_backend_runtime_milestone_not_single_active_runtime"
    assert phase["completed_automation_pr"] == "POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY"
    assert phase["current_automation_track"] == "POST-SCALE-160-FASTUI-SHELL-MVP"
    assert phase["next_automation_track"] == "POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP"
    assert phase["completed_phase"] == "stable_runtime_mutation_apply"
    assert phase["automation_phase"] == "practical_full_automation_experience"
    assert phase["default_runtime_level"] == "level_4_self_improvement_platform"
    assert phase["max_runtime_level"] == "level_8_fully_autonomous_code_agent"
    assert phase["next_level_advancement_pr"] == "POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT"
    assert phase["final_goal"] == "fully_autonomous_code_agent"
    assert phase["self_improvement_goal"] == "self_improving_codeagentpersonal_kasanecore"
    assert phase["backend_workflow_state_authoritative"] is True
    assert phase["vue_source_of_truth"] is False
    assert phase["vue_execution_capability"] == "none"
    assert phase["direct_merge_enabled"] is False
    assert phase["remote_git_push_enabled"] is False
    assert phase["self_apply_enabled"] is False
    assert phase["stable_runtime_mutation_enabled"] is False
    assert phase["stable_runtime_mutation_performed"] is False
    assert phase["runtime_level_by_profile"]["autonomous_dev_agent"] == "level_8_fully_autonomous_code_agent"
    assert phase["level8_activation_requires"]["profile_selection_alone_starts_loop"] is False

    assert ui_manifest["final_goal"] == phase["final_goal"]
    assert ui_manifest["self_improvement_scope"] == phase["self_improvement_goal"]

    for path in DELETED_DUPLICATE_DOCS:
        assert not path.exists(), f"duplicate planning doc must stay deleted: {path}"

    for token in [
        "single human-readable source of truth",
        f"- Completed automation PR: {phase['completed_automation_pr']}",
        f"- Current automation track: {phase['current_automation_track']}",
        f"- Next automation track: {phase['next_automation_track']}",
        "Runtime level model: profile-dependent",
        "fully_autonomous_code_agent",
        "self_improving_codeagentpersonal_kasanecore",
        "PR-B is allowed only when",
        "POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP",
    ]:
        assert token in master, token

    active_policy = _section(
        policy,
        "## Current execution boundary",
        "## Historical baseline after PR-ATLAS-SCALE-152",
    )
    for token in [
        f"Completed automation PR: {phase['completed_automation_pr']}",
        f"Current automation track: {phase['current_automation_track']}",
        f"Next automation track: {phase['next_automation_track']}",
        "Runtime level model: profile-dependent",
        "Current level semantics: maximum backend milestone reached",
        "Default runtime level: level_4_self_improvement_platform",
        "Max runtime level: level_8_fully_autonomous_code_agent",
        "Profile selection alone never starts an autonomous loop",
    ]:
        assert token in active_policy, token
    for stale in [
        "Current automation track: PR-ATLAS-SCALE-153",
        "Next automation track: PR-ATLAS-SCALE-153",
        "Current level: Level 4 self-improvement platform checkpoint",
        "Target level: Level 4 self-improvement platform checkpoint",
        "Next level advancement checkpoint: PR-ATLAS-SCALE-157",
    ]:
        assert stale not in active_policy, stale

    assert "## Historical baseline after PR-ATLAS-SCALE-152" in policy
    assert "## Historical Non-Negotiable Safety Invariants After PR-ATLAS-SCALE-152" in policy
    assert "direct merge remains disabled" in policy
    assert "critical events always require user judgment" in policy

    assert "Current automation track PR:\n- PR-ATLAS-SCALE-94" not in master
    assert "Next automation track PR:\n- PR-ATLAS-SCALE-94" not in master
    assert "next PR may add local-only diff label conflict export" not in master
    assert "next PR may add local-only diff label conflict export" not in policy

    planned = {item["pr"]: item for item in phase["planned_prs"]}
    for pr in [f"PR-ATLAS-SCALE-{i}" for i in range(113, 161)]:
        assert pr in planned, f"missing planned PR: {pr}"
        assert pr in master, f"master plan missing {pr}"
    for pr in [
        "POST-SCALE-160-PRACTICAL-AUTOMATION-PLAN",
        "POST-SCALE-160-FASTUI-SHELL-MVP",
        "POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP",
        "POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT",
        "POST-SCALE-160-CLAUDE-CHAT-COMPLETE-AUTOMATION-PROFILE",
    ]:
        assert pr in planned, f"missing planned PR: {pr}"

    assert planned["PR-ATLAS-SCALE-127"]["runtime_change_allowed"] is True
    assert planned["PR-ATLAS-SCALE-146"]["runtime_change_allowed"] is True
    assert planned["POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP"]["runtime_change_allowed"] is True


if __name__ == "__main__":
    validate()
    print("Atlas automation plan contract OK")
