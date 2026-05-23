from pathlib import Path

DOCS = [
    "docs/atlas_development_handoff.md",
    "docs/atlas_scale_master_roadmap.md",
    "docs/atlas_autonomous_execution_readiness_policy.md",
    "docs/atlas_thinui_readiness.md",
]


def test_scale_94_docs_pointer_and_boundary() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding="utf-8").lower()
        assert ("completed automation pr: pr-atlas-scale-95" in text) or ("completed automation pr: pr-atlas-scale-96" in text) or ("completed automation pr: pr-atlas-scale-97" in text)
        assert ("current automation track: pr-atlas-scale-96" in text) or ("completed automation pr: pr-atlas-scale-97" in text) or ("current automation track: pr-atlas-scale-97" in text)
        assert ("next automation track: pr-atlas-scale-96" in text) or ("completed automation pr: pr-atlas-scale-97" in text) or ("next automation track: pr-atlas-scale-97" in text)
        assert "disabled backend skeleton" in text
        assert "no execution endpoint" in text
        assert "level-1" in text and "disabled" in text
        assert "runtime remains level_0_manual_only" in text
        assert "autonomous execution" in text and "disabled" in text
        assert "workflow_state remains authoritative" in text or "workflow state remains authoritative" in text
        assert "vue execution capability remains none" in text
        assert "readiness" in text and "execution" in text
