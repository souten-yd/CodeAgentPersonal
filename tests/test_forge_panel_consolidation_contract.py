"""Contract: Lumen Models + Echo ASR/TTS panels are consolidated into Forge mode.

This is a UI-consolidation-only change (data and endpoints unchanged): Forge mode shows the side
panel with the existing Models / ASR / TTS tabs, reusing their panels and refresh functions. These
text-level contracts guard the wiring so a future refactor cannot silently drop the consolidation.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_HTML = (ROOT / "ui.html").read_text(encoding="utf-8")
PANELS_JS = (ROOT / "web" / "js" / "panels.js").read_text(encoding="utf-8")


def test_forge_panel_tab_buttons_exist():
    for btn_id, sub in (("tab-btn-forge-models", "models"), ("tab-btn-forge-asr", "asr"), ("tab-btn-forge-tts", "tts")):
        assert f'id="{btn_id}"' in UI_HTML
        assert f"switchTab('{sub}')" in UI_HTML


def test_forge_panel_tab_ids_and_mode_mapping_registered():
    assert "_FORGE_PANEL_TAB_IDS = ['tab-btn-forge-models','tab-btn-forge-asr','tab-btn-forge-tts']" in UI_HTML
    # MODE_PANEL_TAB_BUTTON_IDS gains a forge entry mapping the three subtabs to the forge buttons.
    forge_map = UI_HTML[UI_HTML.index("forge: {", UI_HTML.index("MODE_PANEL_TAB_BUTTON_IDS")):]
    forge_map = forge_map[: forge_map.index("}")]
    assert "models: 'tab-btn-forge-models'" in forge_map
    assert "asr: 'tab-btn-forge-asr'" in forge_map
    assert "tts: 'tab-btn-forge-tts'" in forge_map


def test_forge_subtabs_declared_for_persistence():
    assert "forge: ['models','asr','tts']" in UI_HTML
    assert "forge: 'models'" in UI_HTML  # default subtab


def test_setmode_forge_shows_panel_and_restores_subtab():
    # Slice the forge branch out of setMode and assert it shows the panel (not display:none) and
    # restores a Forge subtab via switchTab.
    start = UI_HTML.index("} else if (m === 'forge') {")
    branch = UI_HTML[start: UI_HTML.index("} else if (m === 'portal') {", start)]
    assert "panelCol.style.display = ''" in branch
    assert "getLastSubtabForMode('forge')" in branch
    assert "switchTab(" in branch


def test_panel_visibility_helper_handles_forge():
    assert "mode === 'forge'" in UI_HTML
    assert "_FORGE_PANEL_TAB_IDS.forEach" in UI_HTML


def test_switchtab_persists_forge_subtab():
    assert "mode === 'forge' ? 'forge'" in PANELS_JS
