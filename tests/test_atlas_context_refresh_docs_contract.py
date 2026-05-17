from pathlib import Path


def test_docs_include_pr43():
    text = Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-43' in text
