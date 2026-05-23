from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
]


def test_scale_98_docs_advanced_to_scale_100_track() -> None:
    for d in DOCS:
        t = Path(d).read_text(encoding='utf-8')
        assert 'Completed automation PR: PR-ATLAS-SCALE-99' in t
        assert 'Current automation track: PR-ATLAS-SCALE-100' in t
        assert 'Next automation track: PR-ATLAS-SCALE-100' in t
