"""Contract: the orphaned Lumen (chat) panel/mobile tab buttons are gone from the DOM.

After the submenu removal, chat mode hid the side panel entirely, leaving the Log/Skill/Memory/
Models tab buttons (desktop `tab-btn-*` and mobile `mob-*`) orphaned in the DOM — never shown by
any mode, since those panels now live in Nexus/Forge. This cleanup deletes those dead buttons and
empties the chat tab-id constants/maps that pointed at them. The shared content panes are kept
(Nexus/Forge still render Log/Skill/Memory/Models through `switchTab`).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_HTML = (ROOT / "ui.html").read_text(encoding="utf-8")

# IDs that were chat-only and are now removed. The `-echo`, `nexus-` and `forge-` variants are
# separate elements owned by other modes and must NOT be matched here.
_REMOVED_BUTTON_IDS = [
    'tab-btn-log',
    'tab-btn-skills',
    'tab-btn-memory',
    'tab-btn-models',
    'mob-log',
    'mob-skills',
    'mob-memory',
    'mob-models',
]


def test_orphaned_chat_tab_buttons_are_removed():
    for btn_id in _REMOVED_BUTTON_IDS:
        assert f'id="{btn_id}"' not in UI_HTML, f"{btn_id} should be removed from the DOM"


def test_chat_panel_tab_id_list_is_empty():
    assert "const _CHAT_PANEL_TAB_IDS = [];" in UI_HTML


def test_chat_mobile_tab_id_list_is_conversation_only():
    assert "const _CHAT_MOB_TAB_IDS = ['mob-chat'];" in UI_HTML


def test_other_modes_keep_their_own_tab_buttons():
    # Sanity: Forge still owns its dedicated panel buttons. (Nexus Memory/Skill/Log moved to the
    # nexus-col subtab row; Echo was reduced to Vault-only, so its log/models-echo buttons are gone.)
    for kept in (
        'id="tab-btn-forge-models"',
        'id="tab-btn-vault"',
    ):
        assert kept in UI_HTML, f"{kept} must be retained"
