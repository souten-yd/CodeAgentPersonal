"""Contract: Lumen (chat) mode no longer shows the side panel submenu.

The Log/Skill/Memory/Models panels were consolidated into Nexus/Forge, so chat mode is just the
conversation — the panel-col side submenu and its resizer are hidden in chat mode. The panel DOM
itself is retained (Echo/Nexus/Forge still use it), only chat's access is removed.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_HTML = (ROOT / "ui.html").read_text(encoding="utf-8")


def _chat_else_branch() -> str:
    # The trailing `else { ... }` of setMode is the chat/default branch.
    anchor = UI_HTML.index("try { window.Portal?.activate?.(); } catch (_e) {}")
    start = UI_HTML.index("} else {", anchor)
    return UI_HTML[start: UI_HTML.index("\n  }", start)]


def test_chat_mode_hides_side_panel_and_resizer():
    branch = _chat_else_branch()
    assert "panelCol.style.display = 'none'" in branch
    assert "resizer.style.display = 'none'" in branch
    # chat-col is still shown (the conversation stays).
    assert "chatCol.style.display  = ''" in branch


def test_chat_mobile_shows_only_conversation_tab():
    assert "const _CHAT_MOB_TAB_IDS = ['mob-chat'];" in UI_HTML
