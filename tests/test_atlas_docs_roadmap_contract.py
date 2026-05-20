from pathlib import Path


def test_atlas_docs_roadmap_contract() -> None:
    roadmap = Path("docs/atlas_scale_master_roadmap.md")
    assert roadmap.exists(), "docs/atlas_scale_master_roadmap.md must exist"
    roadmap_text = roadmap.read_text(encoding="utf-8")

    for marker in [
        "PR-ATLAS-SCALE-64",
        "PR-73",
        "PR-82",
        "Autonomous Development Platform",
        "Workspace Snapshot & Restore Foundation",
        "Self-Improving CodeAgent Platform",
    ]:
        assert marker in roadmap_text, f"Missing roadmap marker: {marker}"

    handoff = Path("docs/atlas_development_handoff.md")
    assert handoff.exists(), "docs/atlas_development_handoff.md must exist"
    handoff_text = handoff.read_text(encoding="utf-8")

    for marker in [
        "PR-ATLAS-SCALE-63B",
        "PR-ATLAS-SCALE-64",
        "no shell=True",
        "no remote git",
        "no auto safe_apply",
        "Inspect main branch files directly",
    ]:
        assert marker in handoff_text, f"Missing handoff marker: {marker}"
