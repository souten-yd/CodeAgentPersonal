"""Contract: Lumen Models + Echo ASR/TTS panels are merged into the Forge subtab row.

Complete move (data/endpoints unchanged): the Models / ASR / TTS panels were moved out of the
shared side panel-col into Forge's own subtab row (Overview = the forge.js shell, plus Models/ASR/
TTS). The panels keep their inner IDs (#tab-models/#tab-asr/#tab-tts) and refresh functions; they
are relocated into #forge-panel-host at load so forge.js (which rewrites #forge-body) never clobbers
them. Forge no longer uses panel-col, so the panels work on desktop AND mobile.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_HTML = (ROOT / "ui.html").read_text(encoding="utf-8")


def test_forge_subtab_row_has_overview_models_asr_tts():
    row = UI_HTML[UI_HTML.index('<div class="forge-subtab-row">'):]
    row = row[: row.index("</div>\n    </div>")]
    for name in ("overview", "models", "asr", "tts"):
        assert f"switchForgeTab('{name}')" in row
        assert f'id="forge-subtab-{name}"' in row


def test_forge_panel_host_exists_and_panels_relocated_at_load():
    assert 'id="forge-panel-host"' in UI_HTML
    fn = UI_HTML[UI_HTML.index("function relocateForgePanels()"):]
    fn = fn[: fn.index("\nfunction ")]
    assert "'tab-models', 'tab-asr', 'tab-tts'" in fn
    assert "host.appendChild(el)" in fn
    assert "relocateForgePanels();" in UI_HTML  # called on load


def test_switchforgetab_handles_panels_and_overview():
    fn = UI_HTML[UI_HTML.index("function switchForgeTab(name) {"):]
    fn = fn[: fn.index("\nfunction ")]
    assert "'overview', 'models', 'asr', 'tts'" in fn
    assert "refreshModelDb()" in fn and "refreshAsrTab()" in fn and "refreshTtsTab()" in fn
    assert "window.Forge?.activate" in fn  # Overview shows the forge.js shell


def test_old_panel_col_forge_tabs_are_gone():
    for dead in ("tab-btn-forge-models", "tab-btn-forge-asr", "tab-btn-forge-tts"):
        assert dead not in UI_HTML
    assert "const _FORGE_PANEL_TAB_IDS = [];" in UI_HTML
    # No forge entry remains in the panel-col button map.
    panel_map = UI_HTML[UI_HTML.index("const MODE_PANEL_TAB_BUTTON_IDS"):]
    panel_map = panel_map[: panel_map.index("};")]
    assert "forge: {" not in panel_map


def test_setmode_forge_does_not_use_panel_col():
    start = UI_HTML.index("} else if (m === 'forge') {")
    branch = UI_HTML[start: UI_HTML.index("} else if (m === 'portal') {", start)]
    assert "panelCol.style.display = 'none'" in branch
    assert "switchForgeTab(" in branch
    assert "getLastSubtabForMode('forge')" in branch


def test_forge_subtabs_declared_for_persistence():
    assert "forge: ['overview','models','asr','tts']" in UI_HTML
    assert "forge: 'overview'" in UI_HTML  # default subtab
