from pathlib import Path

def test_checkpoint_mentions_pr50b_and_next_pr51():
    text=Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-50B' in text
    assert 'Next PR: PR-51 Optional bounded retry after failed supervised handoff verification' in text
