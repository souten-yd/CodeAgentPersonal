from pathlib import Path


def test_legacy_fallback_helper_contract_and_no_raw_source() -> None:
    main_text = Path('main.py').read_text(encoding='utf-8')

    assert 'def serve_existing_ui_index()' in main_text
    assert 'if os.path.exists(index):' in main_text
    assert 'return FileResponse(index, media_type="text/html"' in main_text
    assert 'return RedirectResponse(ATLAS_NEXT_LEGACY_UI_ROUTE)' in main_text
    assert 'return serve_existing_ui_index()' in main_text

    assert 'web/atlas-next/src' not in main_text
    assert 'raw source' not in main_text.lower()
