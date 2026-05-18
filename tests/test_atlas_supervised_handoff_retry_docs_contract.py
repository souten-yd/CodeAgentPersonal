from pathlib import Path

def test_checkpoint_mentions_pr51b_and_next():
    t=Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-51B' in t
    assert 'PR-ATLAS-PIPE-52' in t
