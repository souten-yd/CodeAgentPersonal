from pathlib import Path

def test_docs_checkpoint_mentions_pr60():
    t=Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8').lower()
    assert 'pr-atlas-pipe-60' in t
