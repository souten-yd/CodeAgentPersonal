from pathlib import Path

def test_ui_html_remains_default_and_no_module_switch() -> None:
    ui = Path('ui.html').read_text(encoding='utf-8').lower()
    assert 'atlas-next' not in ui or 'type="module"' not in ui

def test_backend_authoritative_and_no_execution_capability_docs() -> None:
    text = Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8')
    assert 'backend workflow_state remains authoritative' in text
    assert 'runtime remains level_0_manual_only' in text
    assert 'Vue execution capability remains none' in text
