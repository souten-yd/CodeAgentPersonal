from pathlib import Path

def test_docs_mentions_pr47():
    p = Path('docs/atlas_unified_autopilot_checkpoint.md')
    t = p.read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-47' in t
    assert 'manual approval' in t.lower()
