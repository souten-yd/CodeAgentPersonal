from pathlib import Path

UI = Path('ui.html').read_text(encoding='utf-8')
CSS = Path('web/css/app.css').read_text(encoding='utf-8')


def _media_blocks(css: str, media: str) -> list[str]:
    blocks = []
    start = 0
    while True:
        start = css.find(media, start)
        if start == -1:
            break
        brace_start = css.index('{', start)
        depth = 0
        for i in range(brace_start, len(css)):
            ch = css[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    blocks.append(css[brace_start + 1:i])
                    start = i + 1
                    break
        else:
            raise AssertionError(f'Unclosed media block: {media}')
    if not blocks:
        raise AssertionError(f'Media block not found: {media}')
    return blocks


def _media_block_with(css: str, media: str, token: str) -> str:
    for block in _media_blocks(css, media):
        if token in block:
            return block
    raise AssertionError(f'Media block {media} containing {token!r} not found')


def test_desktop_grid_contract_for_app_body_and_areas():
    desktop = _media_block_with(CSS, '@media(min-width:769px)', '.app-body{')
    assert '.app-body{' in desktop
    assert 'display:grid;' in desktop
    assert 'grid-template-areas:"main resizer side";' in desktop


def test_desktop_grid_area_mappings_for_main_side_and_resizer():
    desktop = _media_block_with(CSS, '@media(min-width:769px)', '.app-body{')
    assert '.chat-col,.echo-col,.agent-col{grid-area:main;' in desktop
    assert '.panel-col{grid-area:side;' in desktop
    assert '.agent-panel-col{grid-area:side;' in desktop
    assert '.panel-resizer{grid-area:resizer;' in desktop


def test_mobile_media_block_still_preserves_stacked_layout_support():
    mobile = _media_block_with(CSS, '@media(max-width:768px)', '.app-body{')
    assert '.app-body{' in mobile
    assert 'display:flex!important;flex-direction:column!important;' in mobile
    assert '.panel-col{' in mobile


def test_panel_tab_labels_files_log_skill_memory_models_present():
    for label in ('Files', 'Log', 'Skill', 'Memory', 'Models'):
        assert f'>{label}<' in UI


def test_panel_structure_not_nested_in_chat_input_container():
    chat_col = UI.split('<div class="chat-col" id="chat-col">', 1)[1].split('<!-- ATLAS MODE -->', 1)[0]
    assert '<div class="panel-col mob-hidden" id="panel-col">' not in chat_col
    assert '<div class="panel-resizer" id="panel-resizer"' not in chat_col

    app_body = UI.split('<div class="app-body">', 1)[1]
    input_pos = app_body.index('<div class="input-area">')
    resizer_pos = app_body.index('<div class="panel-resizer" id="panel-resizer"')
    panel_pos = app_body.index('<div class="panel-col mob-hidden" id="panel-col">')

    assert input_pos < resizer_pos < panel_pos
