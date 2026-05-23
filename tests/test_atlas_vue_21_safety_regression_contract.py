from pathlib import Path

def test_no_server_startup_npm_build_and_ui_legacy_still_present() -> None:
    server_text = Path('app/server.py').read_text(encoding='utf-8').lower()
    assert 'npm run build' not in server_text
    assert 'npm install' not in server_text

    ui = Path('ui.html').read_text(encoding='utf-8').lower()
    assert '<html' in ui
