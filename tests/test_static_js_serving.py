from fastapi.testclient import TestClient

import main
from tests.helpers.ui_contract import load_root_ui_html_text


JS_PATH = "/static/js/app.js"
BOOTSTRAP_TOKEN = "KASANE_UI_BOOTSTRAP_LOADED"
MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS = (
    "function showTaskOptions",
    "async function chooseTaskOption",
    "async function refreshSkills",
    "function renderSkills",
    "async function deleteSkill",
    "async function refreshMemory",
    "async function searchMemory",
    "function renderMemory",
    "async function deleteMemory",
    "function showAddMemoryForm",
    "function hideAddMemoryForm",
    "async function saveNewMemory",
    "async function editMemoryInline",
)
MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS = (
    "function openSettings",
    "function closeSettings",
)
MOVED_SETTINGS_MODAL_WINDOW_EXPORTS = (
    "window.openSettings = openSettings",
    "window.closeSettings = closeSettings",
)


def test_app_js_is_served_with_expected_bootstrap_token():
    client = TestClient(main.app)

    response = client.get(JS_PATH)

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "").lower()
    assert "javascript" in content_type or "text/plain" in content_type
    assert BOOTSTRAP_TOKEN in response.text


def test_ui_html_loads_external_app_js():
    ui_html = load_root_ui_html_text()

    assert f'<script src="{JS_PATH}"></script>' in ui_html


def test_ui_html_does_not_redefine_moved_skills_memory_and_settings_functions():
    ui_html = load_root_ui_html_text()

    for function_definition in (
        *MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
    ):
        assert function_definition not in ui_html


def test_app_js_serves_moved_skills_memory_and_settings_tokens():
    client = TestClient(main.app)

    response = client.get(JS_PATH)

    assert response.status_code == 200
    tokens = [
        *MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_WINDOW_EXPORTS,
        "window.refreshSkills",
        "window.renderMemory",
        "window.showTaskOptions",
    ]
    for token in tokens:
        assert token in response.text
