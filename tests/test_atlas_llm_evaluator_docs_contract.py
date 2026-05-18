from pathlib import Path


def test_docs_mentions_pr44c_and_events():
    text = Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-44C' in text
    assert 'evaluator_completed' in text
    assert 'evaluator_fallback_used' in text
