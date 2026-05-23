from pathlib import Path
import json


def test_atlas_vue_defaultization_roadmap_contract() -> None:
    roadmap = Path("docs/atlas_scale_master_roadmap.md").read_text(encoding="utf-8")

    for marker in [
        "Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-21",
        "Current UI track: Vue defaultization complete",
        "Planned UI track: return to PR-ATLAS-SCALE-106 automation track",
        "Current automation track: PR-ATLAS-SCALE-106",
        "/` is guarded Atlas Next default only when validated dist passes",
        "invalid/missing Vue dist falls back safely to legacy UI",
        "legacy UI remains available via /ui/",
        "`/atlas-next` remains guarded preview route",
        "runtime remains level_0_manual_only",
        "Vue execution capability remains none",
        "VUE21 completed default-enable only, not execution-enable",
        "next work is PR-ATLAS-SCALE-106",
        "fully autonomous code agent",
        "goal → research → plan → implement → test → fix → PR",
        "Self-improving CodeAgentPersonal / KasaneCore remains explicitly in scope",
        "Backend workflow_state remains authoritative",
        "Do not add execute-all, auto-continue, or autonomous execution",
        "Remote git/PR creation/merge remain disabled",
        "available_actions remain metadata-only",
        "must not become another large dashboard",
        "minimal UI policy",
        "minimal_workflow` + `safety_always_visible`",
        "directly support the final user flow",
        "Direct subsystem buttons must not appear in minimal/default mode",
    ]:
        assert marker in roadmap


def test_vue_migration_plan_minimal_policy_contract() -> None:
    plan = Path("docs/atlas_vue_migration_plan.md").read_text(encoding="utf-8")
    for marker in [
        "docs/atlas_autonomous_first_ui_policy.md",
        "must not become another large dashboard",
        "Default-visible Vue UI remains `minimal_workflow` + `safety_always_visible` only",
        "Advanced execution controls, raw JSON, internal IDs, direct subsystem panels, diagnostics, and debug controls remain hidden by default",
        "Direct subsystem buttons must not appear in minimal/default mode",
        "Vue must not compute execution eligibility",
        "Backend workflow_state remains authoritative",
        "No execute-all, no auto-continue, and no autonomous execution",
    ]:
        assert marker in plan


def test_ui_surface_manifest_minimal_mode_still_enforced() -> None:
    manifest = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    assert manifest["default_mode"] == "minimal"
