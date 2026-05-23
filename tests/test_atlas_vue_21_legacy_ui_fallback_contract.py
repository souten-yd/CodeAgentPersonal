from pathlib import Path

def test_legacy_ui_fallback_contract() -> None:
    text = Path('main.py').read_text(encoding='utf-8')
    assert 'def serve_existing_ui_index()' in text
    assert 'return RedirectResponse(ATLAS_NEXT_LEGACY_UI_ROUTE)' in text
    assert 'return serve_existing_ui_index()' in text
