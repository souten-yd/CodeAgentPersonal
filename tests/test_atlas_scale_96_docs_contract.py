from pathlib import Path
DOCS=['docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_autonomous_execution_readiness_policy.md','docs/atlas_thinui_readiness.md']

def test_scale_96_docs_track_pointers() -> None:
    for doc in DOCS:
        t=Path(doc).read_text()
        assert 'Completed automation PR: PR-ATLAS-SCALE-96' in t
        assert 'Current automation track: PR-ATLAS-SCALE-97' in t
        assert 'Next automation track: PR-ATLAS-SCALE-97' in t
