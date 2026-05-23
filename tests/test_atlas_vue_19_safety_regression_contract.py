from pathlib import Path

def test_ui_default_route_and_execution_boundary_markers() -> None:
    ui = Path('ui.html').read_text(encoding='utf-8').lower()
    assert 'atlas-next' not in ui or 'type="module"' not in ui

    docs = Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8')
    assert '/` is guarded Atlas Next default only when validated dist passes' in docs
    assert 'backend workflow_state remains authoritative' in docs
    assert 'runtime remains level_0_manual_only' in docs
    assert 'Vue execution capability remains none' in docs
