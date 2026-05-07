from fastapi.testclient import TestClient

import main
from tests.helpers.ui_contract import load_root_ui_html_text
from tests.helpers.ui_js_contract import (
    APP_JS_PATH,
    MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
    MOVED_SETTINGS_MODAL_WINDOW_EXPORTS,
    MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
    MOVED_SETTINGS_TAB_WINDOW_EXPORTS,
    MOVED_SETTINGS_UI_HELPER_FUNCTION_DEFINITIONS,
    MOVED_SETTINGS_UI_HELPER_WINDOW_EXPORTS,
    MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
    MOVED_SKILLS_AND_MEMORY_STATE_TOKENS,
    MOVED_SKILLS_AND_MEMORY_WINDOW_EXPORTS,
    PANELS_JS_PATH,
    SETTINGS_JS_PATH,
    SKILLS_MEMORY_JS_PATH,
)


BOOTSTRAP_TOKEN = "KASANE_UI_BOOTSTRAP_LOADED"


def _fetch_js(path: str) -> str:
    client = TestClient(main.app)
    response = client.get(path)
    assert response.status_code == 200
    return response.text


def test_ui_html_loads_external_app_settings_skills_memory_and_panels_js_in_order():
    ui_html = load_root_ui_html_text()

    app_script = f'<script src="{APP_JS_PATH}"></script>'
    settings_script = f'<script src="{SETTINGS_JS_PATH}"></script>'
    skills_memory_script = f'<script src="{SKILLS_MEMORY_JS_PATH}"></script>'
    panels_script = f'<script src="{PANELS_JS_PATH}"></script>'
    assert app_script in ui_html
    assert settings_script in ui_html
    assert skills_memory_script in ui_html
    assert panels_script in ui_html
    assert ui_html.index(app_script) < ui_html.index(settings_script)
    assert ui_html.index(settings_script) < ui_html.index(skills_memory_script)
    assert ui_html.index(skills_memory_script) < ui_html.index(panels_script)


def test_ui_html_does_not_redefine_moved_skills_memory_and_settings_functions():
    ui_html = load_root_ui_html_text()

    for function_definition in (
        *MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_UI_HELPER_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
    ):
        assert function_definition not in ui_html


def test_app_js_keeps_bootstrap_without_moved_feature_tokens():
    app_js = _fetch_js(APP_JS_PATH)

    assert BOOTSTRAP_TOKEN in app_js

    for token in (
        *MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_WINDOW_EXPORTS,
        *MOVED_SETTINGS_UI_HELPER_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_UI_HELPER_WINDOW_EXPORTS,
        *MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
        *MOVED_SKILLS_AND_MEMORY_STATE_TOKENS,
        *MOVED_SKILLS_AND_MEMORY_WINDOW_EXPORTS,
        *MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_TAB_WINDOW_EXPORTS,
    ):
        assert token not in app_js


def test_settings_js_owns_settings_modal_and_ui_helper_tokens_only():
    settings_js = _fetch_js(SETTINGS_JS_PATH)

    for token in (
        *MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_WINDOW_EXPORTS,
        *MOVED_SETTINGS_UI_HELPER_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_UI_HELPER_WINDOW_EXPORTS,
    ):
        assert token in settings_js

    for token in (
        BOOTSTRAP_TOKEN,
        *MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
        *MOVED_SKILLS_AND_MEMORY_STATE_TOKENS,
        *MOVED_SKILLS_AND_MEMORY_WINDOW_EXPORTS,
        *MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_TAB_WINDOW_EXPORTS,
    ):
        assert token not in settings_js


def test_skills_memory_js_owns_skills_memory_tokens_only():
    skills_memory_js = _fetch_js(SKILLS_MEMORY_JS_PATH)

    for token in (
        *MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
        *MOVED_SKILLS_AND_MEMORY_STATE_TOKENS,
        *MOVED_SKILLS_AND_MEMORY_WINDOW_EXPORTS,
    ):
        assert token in skills_memory_js

    for token in (
        BOOTSTRAP_TOKEN,
        *MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_WINDOW_EXPORTS,
        *MOVED_SETTINGS_UI_HELPER_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_UI_HELPER_WINDOW_EXPORTS,
        *MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_TAB_WINDOW_EXPORTS,
    ):
        assert token not in skills_memory_js


def test_panels_js_owns_settings_tab_tokens():
    panels_js = _fetch_js(PANELS_JS_PATH)

    for token in (
        *MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_TAB_WINDOW_EXPORTS,
    ):
        assert token in panels_js
