from fastapi.testclient import TestClient

import main
from tests.helpers.ui_contract import load_root_ui_html_text, load_ui_contract_text


APP_JS_PATH = "/static/js/app.js"
SETTINGS_JS_PATH = "/static/js/settings.js"
SKILLS_MEMORY_JS_PATH = "/static/js/skills_memory.js"
PANELS_JS_PATH = "/static/js/panels.js"
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
MOVED_SKILLS_AND_MEMORY_STATE_TOKENS = (
    "var _taskOptionsMap",
    "var _memSearchTimer",
    "var _catColor",
    "var _catLabel",
)
MOVED_SKILLS_AND_MEMORY_WINDOW_EXPORTS = (
    "window.showTaskOptions = showTaskOptions",
    "window.chooseTaskOption = chooseTaskOption",
    "window._taskOptionsMap = _taskOptionsMap",
    "window.refreshSkills = refreshSkills",
    "window.renderSkills = renderSkills",
    "window.deleteSkill = deleteSkill",
    "window.refreshMemory = refreshMemory",
    "window.searchMemory = searchMemory",
    "window.renderMemory = renderMemory",
    "window.deleteMemory = deleteMemory",
    "window.showAddMemoryForm = showAddMemoryForm",
    "window.hideAddMemoryForm = hideAddMemoryForm",
    "window.saveNewMemory = saveNewMemory",
    "window.editMemoryInline = editMemoryInline",
    "window._memSearchTimer = _memSearchTimer",
    "window._catColor = _catColor",
    "window._catLabel = _catLabel",
)
MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS = (
    "function openSettings",
    "function closeSettings",
)
MOVED_SETTINGS_MODAL_WINDOW_EXPORTS = (
    "window.openSettings = openSettings",
    "window.closeSettings = closeSettings",
)
MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS = (
    "function switchTab",
)
MOVED_SETTINGS_TAB_WINDOW_EXPORTS = (
    "window.switchTab = switchTab",
)

SWITCH_TAB_GLOBAL_DEPENDENCY_TOKENS = (
    ("function _setPanelTabActiveButton",),
    ("function refreshFileBrowser", "async function refreshFileBrowser"),
    ("function refreshProjectFileManager", "async function refreshProjectFileManager"),
    ("function refreshSkills", "async function refreshSkills"),
    ("function refreshMemory", "async function refreshMemory"),
    ("function refreshModelDb", "async function refreshModelDb"),
    ("function refreshModelRoles", "async function refreshModelRoles"),
    ("function refreshEchoVault", "async function refreshEchoVault"),
    ("function refreshAsrTab", "async function refreshAsrTab"),
    ("function refreshTtsTab", "async function refreshTtsTab"),
)


def test_app_js_is_served_with_expected_bootstrap_token():
    client = TestClient(main.app)

    response = client.get(APP_JS_PATH)

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "").lower()
    assert "javascript" in content_type or "text/plain" in content_type
    assert BOOTSTRAP_TOKEN in response.text


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
        *MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
    ):
        assert function_definition not in ui_html


def test_app_js_keeps_bootstrap_without_moved_feature_tokens():
    client = TestClient(main.app)

    response = client.get(APP_JS_PATH)

    assert response.status_code == 200
    assert BOOTSTRAP_TOKEN in response.text

    for token in (
        *MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_WINDOW_EXPORTS,
        *MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
        *MOVED_SKILLS_AND_MEMORY_STATE_TOKENS,
        *MOVED_SKILLS_AND_MEMORY_WINDOW_EXPORTS,
        *MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_TAB_WINDOW_EXPORTS,
    ):
        assert token not in response.text


def test_settings_js_serves_settings_modal_tokens_and_window_exports():
    client = TestClient(main.app)

    response = client.get(SETTINGS_JS_PATH)

    assert response.status_code == 200
    for token in (
        *MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_WINDOW_EXPORTS,
    ):
        assert token in response.text

    for token in (
        BOOTSTRAP_TOKEN,
        *MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
        *MOVED_SKILLS_AND_MEMORY_STATE_TOKENS,
        *MOVED_SKILLS_AND_MEMORY_WINDOW_EXPORTS,
        *MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_TAB_WINDOW_EXPORTS,
    ):
        assert token not in response.text


def test_skills_memory_js_serves_skills_memory_tokens_and_window_exports():
    client = TestClient(main.app)

    response = client.get(SKILLS_MEMORY_JS_PATH)

    assert response.status_code == 200
    for token in (
        *MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS,
        *MOVED_SKILLS_AND_MEMORY_STATE_TOKENS,
        *MOVED_SKILLS_AND_MEMORY_WINDOW_EXPORTS,
    ):
        assert token in response.text

    for token in (
        BOOTSTRAP_TOKEN,
        *MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_MODAL_WINDOW_EXPORTS,
        *MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS,
        *MOVED_SETTINGS_TAB_WINDOW_EXPORTS,
    ):
        assert token not in response.text


def test_ui_contract_keeps_switch_tab_global_dependencies_visible_after_js_split():
    contract_text = load_ui_contract_text()

    for alternatives in SWITCH_TAB_GLOBAL_DEPENDENCY_TOKENS:
        assert any(token in contract_text for token in alternatives), alternatives


def test_panels_js_serves_switch_tab_definition_and_window_export():
    client = TestClient(main.app)

    response = client.get(PANELS_JS_PATH)

    assert response.status_code == 200
    assert "function switchTab" in response.text
    assert "window.switchTab = switchTab" in response.text
