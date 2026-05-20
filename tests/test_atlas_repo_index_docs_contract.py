from pathlib import Path

def test_docs_mentions_pr61():
    text=Path('docs/atlas_autopilot_current_status.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-SCALE-61' in text
