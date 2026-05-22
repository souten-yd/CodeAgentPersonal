from pathlib import Path

DOCS = [
    "docs/atlas_scale_master_roadmap.md",
    "docs/atlas_vue_migration_plan.md",
    "docs/atlas_thinui_readiness.md",
    "docs/atlas_development_handoff.md",
]

REQUIRED = [
    "## Current Atlas Vue UI Track State",
    "Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-15",
    "Current UI track: PR-ATLAS-VUE-16",
    "Planned UI track: PR-ATLAS-VUE-16 through PR-ATLAS-VUE-21",
    "Current automation track: PR-ATLAS-SCALE-93",
    "Existing ui.html remains default until PR-ATLAS-VUE-21",
    "Vue remains parallel/read-only/not default",
    "/atlas-next remains mounted/guarded/dist-backed/fail-closed/non-default",
    "diagnostics endpoint remains GET-only/metadata-only",
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
