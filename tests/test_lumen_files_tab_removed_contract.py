"""Contract: the Lumen Files panel tab is removed from the UI.

The Files *tab* (panel-col File Manager) is deleted from the chat panel. The backend file
operations (list_files/read_file/edit_file and /projects/.../files) are intentionally KEPT — they
are used by Agent/project features — so this is a UI-only removal. Log becomes the default panel.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_HTML = (ROOT / "ui.html").read_text(encoding="utf-8")
MAIN_PY = (ROOT / "main.py").read_text(encoding="utf-8")


def test_files_tab_button_and_content_removed():
    assert 'id="tab-btn-files"' not in UI_HTML
    assert 'id="tab-files"' not in UI_HTML
    assert 'id="mob-files"' not in UI_HTML
    assert "switchTab('files')" not in UI_HTML


def test_files_dropped_from_tab_registries():
    assert "const _CHAT_PANEL_TAB_IDS = ['tab-btn-log','tab-btn-skills','tab-btn-memory','tab-btn-models']" in UI_HTML
    assert "const _CHAT_MOB_TAB_IDS = ['mob-chat','mob-log','mob-skills','mob-memory','mob-models']" in UI_HTML
    assert "chat: ['chat','log','skills','memory','models']" in UI_HTML
    # chat panel-button mapping no longer maps files.
    chat_map = UI_HTML[UI_HTML.index("chat: {", UI_HTML.index("MODE_PANEL_TAB_BUTTON_IDS")):]
    chat_map = chat_map[: chat_map.index("}")]
    assert "files:" not in chat_map


def test_log_is_default_active_panel():
    assert '<button class="tab-btn active" id="tab-btn-log"' in UI_HTML
    assert '<div class="tab-content active" id="tab-log">' in UI_HTML


def test_backend_file_operations_are_retained():
    # UI-only removal: the backend file ops + project files endpoint stay (used elsewhere).
    assert "def list_files(" in MAIN_PY
    assert "def read_file(" in MAIN_PY
    # The project files manager helper remains defined and guarded for any remaining callers.
    assert "function refreshProjectFileManager" in UI_HTML
    assert "const list = document.getElementById('fm-list');" in UI_HTML
