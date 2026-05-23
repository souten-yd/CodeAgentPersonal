from pathlib import Path

def test_ui_default_and_non_default_route_safety_markers_preserved() -> None:
    ui = Path('ui.html').read_text(encoding='utf-8').lower()
    assert 'atlas-next' not in ui or 'type="module"' not in ui

    docs = Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8')
    assert '/atlas-next remains mounted/guarded/dist-backed/fail-closed/non-default' in docs
    assert 'Vue execution capability remains none' in docs
    assert 'backend workflow_state remains authoritative' in docs
