"""Contract: the Lumen Files panel tab is removed from the UI.

The Files *tab* (panel-col File Manager) is deleted from the chat panel. The backend file
operations (list_files/read_file/edit_file and /projects/.../files) are intentionally KEPT — they
are used by Agent/project features — so this is a UI-only removal.
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
    # 'files' must not reappear in any chat tab registry. (The chat registries were later emptied
    # entirely when Lumen became conversation-only — see test_lumen_orphan_chat_tabs_removed_contract
    # — so the strongest invariant that survives is simply: no 'files' subtab anywhere.)
    assert "'files'" not in UI_HTML or "switchTab('files')" not in UI_HTML
    assert "mob-files" not in UI_HTML
    # chat no longer has a panel-button mapping at all (no Log/Skill/Memory/Models/Files tabs).
    panel_map = UI_HTML[UI_HTML.index("const MODE_PANEL_TAB_BUTTON_IDS"):]
    panel_map = panel_map[: panel_map.index("};")]
    assert "files:" not in panel_map


def test_backend_file_operations_are_retained():
    # UI-only removal: the backend file ops + project files endpoint stay (used elsewhere).
    assert "def list_files(" in MAIN_PY
    assert "def read_file(" in MAIN_PY
    # The project files manager helper remains defined and guarded for any remaining callers.
    assert "function refreshProjectFileManager" in UI_HTML
    assert "const list = document.getElementById('fm-list');" in UI_HTML
