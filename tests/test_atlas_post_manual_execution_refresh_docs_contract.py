from pathlib import Path

def test_docs_contract_mentions_pr58():
    t=Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-58' in t
