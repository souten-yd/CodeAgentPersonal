from pathlib import Path

def test_checkpoint_mentions_pr50():
    text=Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-50' in text
