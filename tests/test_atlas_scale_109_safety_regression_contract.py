from pathlib import Path


def test_debug_desktop_lumen_visibility_and_layout_contracts_preserved():
    main_text = Path('main.py').read_text(encoding='utf-8')
    css_text = Path('web/css/app.css').read_text(encoding='utf-8')
    assert 'desktop_lumen_input_visible' in main_text
    assert '.app-body{display:flex;flex-direction:row;align-items:stretch}' in css_text
    assert '@media(min-width:769px)' in css_text
