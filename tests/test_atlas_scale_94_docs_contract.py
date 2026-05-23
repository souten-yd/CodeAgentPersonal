from pathlib import Path

DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
]

def test_scale_94_docs_pointer_and_boundary() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8').lower()
        assert 'pr-atlas-scale-94 completed' in text
        assert 'current automation track: pr-atlas-scale-95' in text
        assert 'next automation track: pr-atlas-scale-95' in text
        assert 'runtime remains level_0_manual_only' in text
        assert 'level-1' in text and 'disabled' in text
