from pathlib import Path

def test_checkpoint_mentions_pr55():
    t=Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-55' in t
    assert 'does not execute next_action' in t or 'does not execute next actions' in t
