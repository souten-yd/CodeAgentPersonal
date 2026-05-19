from pathlib import Path

def test_docs_mentions_pr56():
    t=Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-56' in t
    assert 'does not execute next actions' in t
