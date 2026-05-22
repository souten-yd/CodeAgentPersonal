from pathlib import Path


def test_atlas_vue_defaultization_roadmap_contract() -> None:
    text = Path("docs/atlas_scale_master_roadmap.md").read_text(encoding="utf-8")

    for marker in [
        "PR-ATLAS-VUE-13",
        "PR-ATLAS-VUE-14",
        "PR-ATLAS-VUE-15",
        "PR-ATLAS-VUE-16",
        "PR-ATLAS-VUE-17",
        "PR-ATLAS-VUE-18",
        "PR-ATLAS-VUE-19",
        "PR-ATLAS-VUE-20",
        "PR-ATLAS-VUE-21",
        "Current UI track is PR-ATLAS-VUE-13",
        "PR-ATLAS-VUE-21 is the default enable checkpoint",
        "Existing ui.html remains default until PR-ATLAS-VUE-21",
        "PR-ATLAS-SCALE-93 remains the current automation track",
        "After PR-ATLAS-VUE-21",
        "fully autonomous code agent",
        "goal → research → plan → implement → test → fix → PR",
        "Self-improving CodeAgentPersonal / KasaneCore remains explicitly in scope",
        "level_0_manual_only",
        "Backend workflow_state remains authoritative",
        "Do not add execute-all, auto-continue, or autonomous execution",
        "Remote git/PR creation/merge remain disabled",
        "Autonomous execution remains disabled",
        "available_actions remain metadata-only",
    ]:
        assert marker in text
