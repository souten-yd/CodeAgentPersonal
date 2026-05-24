from pathlib import Path

UI = Path('ui.html').read_text(encoding='utf-8')
CSS = Path('web/css/app.css').read_text(encoding='utf-8')
MAIN = Path('main.py').read_text(encoding='utf-8')


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


def test_desktop_flex_contract_for_app_body_and_columns():
    desktop = _media_block_with(CSS, '@media(min-width:769px)', '.app-body{')
    assert '.app-body{display:flex;flex-direction:row;align-items:stretch}' in desktop
    assert '.chat-col,.echo-col,.agent-col{flex:1 1 auto;min-width:0;border-right:1px solid var(--border)}' in desktop
    assert '.nexus-col{flex:1 1 auto;min-width:0}' in desktop


def test_desktop_panel_column_width_contract_and_resizer_visibility():
    desktop = _media_block_with(CSS, '@media(min-width:769px)', '.panel-col{')
    assert '.panel-col{flex:0 0 var(--panel-col-width, min(46vw, 560px));min-width:260px;max-width:75vw}' in desktop
    assert '.agent-panel-col{flex:0 0 min(42vw, 520px);min-width:240px;max-width:70vw}' in desktop
    assert '.panel-resizer{display:block}' in desktop


def test_chat_column_flex_stack_contract_for_messages_and_input():
    assert '.chat-col{display:flex;flex-direction:column;' in CSS
    assert '.messages{flex:1;min-height:0;overflow-y:auto;' in CSS
    assert '.input-area{' in CSS
    assert 'flex-shrink:0;' in CSS


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


def test_chat_column_contains_messages_and_input_area_structure():
    chat_col = UI.split('<div class="chat-col" id="chat-col">', 1)[1].split('<!-- ATLAS MODE -->', 1)[0]
    assert 'class="messages"' in chat_col and 'id="messages"' in chat_col
    assert '<div class="input-area">' in chat_col
    assert '<textarea id="input"' in chat_col


def test_desktop_mode_switch_clears_mobile_hidden_classes_for_columns():
    assert "if (window.innerWidth > 768) {" in UI
    for token in (
        "chatCol?.classList.remove('mob-hidden');",
        "panelCol?.classList.remove('mob-hidden');",
        "echoCol?.classList.remove('mob-hidden');",
        "agentCol?.classList.remove('mob-hidden');",
        "agentPanelCol?.classList.remove('mob-hidden');",
        "atlasPanelCol?.classList.remove('mob-hidden');",
        "nexusCol?.classList.remove('mob-hidden');",
    ):
        assert token in UI


def test_debug_tests_surface_includes_desktop_lumen_visibility_check():
    assert "/debug/tests" in MAIN
    assert "desktop_lumen_input_visible" in MAIN
    assert "desktop-lumen-input" in MAIN


def test_debug_tests_surface_excludes_stale_grid_only_listing():
    assert "grid-template-areas" not in MAIN[MAIN.find('def debug_tests_home'):MAIN.find('def debug_tests_run_all')]
