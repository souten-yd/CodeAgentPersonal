from pathlib import Path

def test_docs_mentions_pr45():
    text = Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-45' in text
