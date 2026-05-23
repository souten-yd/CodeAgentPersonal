from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_thinui_readiness.md',
]


def test_vue_defaultization_remains_guarded_non_execution() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert '/` is guarded Atlas Next default only when validated dist passes' in text
        assert 'invalid/missing Vue dist falls back safely to legacy UI' in text
        assert 'legacy UI remains available via /ui/' in text
        assert 'VUE21 completed default-enable only, not execution-enable' in text


def test_no_enabled_autonomous_execution_wording_is_introduced() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8').lower()
        assert 'execute-all enabled' not in text
        assert 'auto-continue enabled' not in text
        assert 'autonomous execution enabled' not in text
