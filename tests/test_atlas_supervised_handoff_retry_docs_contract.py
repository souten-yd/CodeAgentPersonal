from pathlib import Path

def test_checkpoint_mentions_pr51():
    t=Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-51' in t
