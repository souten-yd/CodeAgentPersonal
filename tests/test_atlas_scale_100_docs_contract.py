from pathlib import Path

DOCS=[
 'docs/atlas_development_handoff.md',
 'docs/atlas_scale_master_roadmap.md',
 'docs/atlas_autonomous_execution_readiness_policy.md',
 'docs/atlas_thinui_readiness.md',
]

def test_docs_track_advances_to_scale_101():
    for d in DOCS:
        t=Path(d).read_text(encoding='utf-8')
        assert 'PR-ATLAS-SCALE-100' in t
        assert 'Current automation track: PR-ATLAS-SCALE-101' in t
        assert 'Next automation track: PR-ATLAS-SCALE-101' in t
