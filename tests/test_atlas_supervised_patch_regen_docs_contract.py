from pathlib import Path

def test_docs_mentions_pr47b_and_manual_approval():
    p = Path('docs/atlas_unified_autopilot_checkpoint.md')
    t = p.read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-47B' in t
    assert 'manual approval' in t.lower()
