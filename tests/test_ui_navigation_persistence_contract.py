import re
from pathlib import Path

UI = Path("ui.html").read_text(encoding="utf-8")
PANELS_JS = Path("web/js/panels.js").read_text(encoding="utf-8")


def test_ui_navigation_local_storage_keys_exist():
    assert "UI_LAST_MODE_KEY" in UI
    assert "kasane:lastMode" in UI
    assert "UI_LAST_SUBTABS_KEY" in UI
    assert "kasane:lastSubtabsByMode" in UI


def test_restore_ui_navigation_state_exists_and_uses_saved_mode_without_resaving():
    assert "function restoreUiNavigationState" in UI
    body = re.search(r"function restoreUiNavigationState\(\) \{(?P<body>.*?)\n\}", UI, re.S).group("body")
    assert "try {" in body
    assert "console.warn('restoreUiNavigationState failed'" in body
    assert "localStorage.getItem(UI_LAST_MODE_KEY)" in body
    assert "const hasValidSavedMode = isValidUiMode(savedMode)" in body
    assert "const targetMode = hasValidSavedMode ? savedMode : 'chat'" in body
    assert "setMode(targetMode, {restore: true, persist: false})" in body
    assert "persist: isValidUiMode(savedMode)" not in body


def test_set_mode_persists_last_mode_after_validation():
    body = re.search(r"function setMode\(m, options = \{\}\) \{(?P<body>.*?)\n\}\n\nfunction switchNexusTab", UI, re.S).group("body")
    assert "if (!isValidUiMode(m)) m = 'chat';" in body
    assert "saveLastMode(m)" in body
    assert "options.persist !== false" in body


def test_mode_aware_subtab_mapping_distinguishes_chat_and_echo_duplicates():
    assert "const MODE_SUBTAB_BUTTON_IDS" in UI
    assert re.search(r"chat:\s*\{[^}]*log:\s*'mob-log'", UI, re.S)
    assert re.search(r"echo:\s*\{[^}]*log:\s*'mob-log-echo'", UI, re.S)
    assert re.search(r"chat:\s*\{[^}]*models:\s*'mob-models'", UI, re.S)
    assert re.search(r"echo:\s*\{[^}]*models:\s*'mob-models-echo'", UI, re.S)
    assert "MODE_PANEL_TAB_BUTTON_IDS" in UI
    assert "tab-btn-log-echo" in UI and "tab-btn-models-echo" in UI


def test_subtab_switching_saves_by_current_mode():
    assert "function saveLastSubtab(currentMode, name)" in UI
    assert "readLastSubtabsByMode" in UI
    assert "saveLastSubtab(mode === 'echo' ? 'echo' : 'chat', name)" in PANELS_JS
    assert "restoreLastSubtabForMode(m," in UI


def test_load_startup_does_not_force_chat_unconditionally():
    load_body = re.search(r"addEventListener\('load', async \(\) => \{(?P<body>.*?)\n\}\);", UI, re.S).group("body")
    forbidden = [
        r"setMode\(\s*['\"]chat['\"]\s*\)",
        r"mobSwitch\(\s*['\"]chat['\"]\s*\)",
        r"switchTab\(\s*['\"]chat['\"]\s*\)",
        r"btn-chat[^\n]+classList\.add\(\s*['\"]active['\"]\s*\)",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, load_body), pattern
    assert "restoreUiNavigationState()" in load_body


def test_load_restores_navigation_before_async_settings_init():
    load_body = re.search(r"addEventListener\('load', async \(\) => \{(?P<body>.*?)\n\}\);", UI, re.S).group("body")
    restore_index = load_body.index("restoreUiNavigationState()")
    settings_index = load_body.index("await loadSettingsFromDb()")
    assert restore_index < settings_index


def test_chat_internal_ids_keep_lumen_user_label():
    assert '''id="btn-chat" onclick="setMode('chat')">Lumen</button>''' in UI
    assert '''id="mob-chat" onclick="mobSwitch('chat')">Lumen</button>''' in UI
    assert '''id="btn-chat" onclick="setMode('chat')">Chat</button>''' not in UI
    assert '''id="mob-chat" onclick="mobSwitch('chat')">Chat</button>''' not in UI
