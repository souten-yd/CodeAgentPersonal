from tests.helpers.ui_contract import load_ui_contract_text
from tests.helpers.ui_js_contract import (
    NEXUS_DISPLAY_HELPER_GLOBAL_DEPENDENCY_TOKENS,
    OPEN_SETTINGS_GLOBAL_DEPENDENCY_TOKENS,
    SETTINGS_UI_HELPER_GLOBAL_DEPENDENCY_TOKENS,
    SWITCH_TAB_GLOBAL_DEPENDENCY_TOKENS,
)


def test_ui_contract_keeps_switch_tab_global_dependencies_visible_after_js_split():
    contract_text = load_ui_contract_text()

    for alternatives in SWITCH_TAB_GLOBAL_DEPENDENCY_TOKENS:
        assert any(token in contract_text for token in alternatives), alternatives


def test_ui_contract_keeps_open_settings_global_dependencies_visible_after_js_split():
    contract_text = load_ui_contract_text()

    for alternatives in OPEN_SETTINGS_GLOBAL_DEPENDENCY_TOKENS:
        assert any(token in contract_text for token in alternatives), alternatives


def test_ui_contract_keeps_settings_ui_helper_global_dependencies_visible_after_js_split():
    contract_text = load_ui_contract_text()

    for alternatives in SETTINGS_UI_HELPER_GLOBAL_DEPENDENCY_TOKENS:
        assert any(token in contract_text for token in alternatives), alternatives


def test_ui_contract_keeps_nexus_display_helper_global_dependencies_visible_after_js_split():
    contract_text = load_ui_contract_text()

    for alternatives in NEXUS_DISPLAY_HELPER_GLOBAL_DEPENDENCY_TOKENS:
        assert any(token in contract_text for token in alternatives), alternatives
