from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
]


def test_docs_advance_to_scale_100_and_record_scale_99_completion():
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'PR-ATLAS-SCALE-99 completed' in text
        assert 'Completed automation PR: PR-ATLAS-SCALE-99' in text
        assert 'Current automation track: PR-ATLAS-SCALE-100' in text
        assert 'Next automation track: PR-ATLAS-SCALE-100' in text
        assert 'level_0_manual_only' in text
