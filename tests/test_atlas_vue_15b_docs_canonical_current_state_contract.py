from pathlib import Path

DOCS = [
    "docs/atlas_scale_master_roadmap.md",
    "docs/atlas_vue_migration_plan.md",
    "docs/atlas_thinui_readiness.md",
    "docs/atlas_development_handoff.md",
]

REQUIRED = [
    "## Current Atlas Vue UI Track State",
    "Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-21",
    "Current UI track: Vue defaultization complete",
    "Planned UI track: return to PR-ATLAS-SCALE-93 automation track",
    "Current automation track: PR-ATLAS-SCALE-93",
    "legacy UI remains available via /ui/",
    "`/` is guarded Atlas Next default only when validated dist passes",
    "/` is guarded Atlas Next default only when validated dist passes",
    "backend workflow_state remains authoritative",
    "backend workflow_state remains authoritative",
    "runtime remains level_0_manual_only",
    "Vue execution capability remains none",
]


def test_vue_15b_docs_canonical_current_state_contract() -> None:
    for path in DOCS:
        text = Path(path).read_text(encoding="utf-8")
        for marker in REQUIRED:
            assert marker in text, f"missing marker in {path}: {marker}"


def test_vue_15b_historical_track_markers_are_labeled() -> None:
    for path in DOCS:
        text = Path(path).read_text(encoding="utf-8")
        assert "Current UI track is PR-ATLAS-VUE-14." not in text
        assert "Current UI track: PR-ATLAS-VUE-14." not in text
        assert "Current UI track is now PR-ATLAS-VUE-15." not in text
