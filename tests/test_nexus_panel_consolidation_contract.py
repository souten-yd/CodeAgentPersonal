"""Contract: Lumen Memory/Skill/Log panels are consolidated into Nexus mode.

UI-consolidation-only change (data/endpoints unchanged): Nexus mode shows the side panel with the
existing Memory / Skill / Log tabs, reusing their panels and refresh functions, alongside Nexus's
own dashboard tabs. These text-level contracts guard the wiring.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_HTML = (ROOT / "ui.html").read_text(encoding="utf-8")
PANELS_JS = (ROOT / "web" / "js" / "panels.js").read_text(encoding="utf-8")


def test_nexus_panel_tab_buttons_exist():
    for btn_id, sub in (("tab-btn-nexus-memory", "memory"), ("tab-btn-nexus-skills", "skills"), ("tab-btn-nexus-log", "log")):
        assert f'id="{btn_id}"' in UI_HTML
        assert f"switchTab('{sub}')" in UI_HTML


def test_nexus_panel_tab_ids_and_mode_mapping_registered():
    assert "_NEXUS_PANEL_TAB_IDS = ['tab-btn-nexus-memory','tab-btn-nexus-skills','tab-btn-nexus-log']" in UI_HTML
    nexus_map = UI_HTML[UI_HTML.index("nexus: {", UI_HTML.index("MODE_PANEL_TAB_BUTTON_IDS")):]
    nexus_map = nexus_map[: nexus_map.index("}")]
    assert "memory: 'tab-btn-nexus-memory'" in nexus_map
    assert "skills: 'tab-btn-nexus-skills'" in nexus_map
    assert "log: 'tab-btn-nexus-log'" in nexus_map


def test_nexus_subtabs_declared_for_persistence():
    # Nexus keeps its own dashboard tab AND gains the consolidated panel subtabs.
    assert "nexus: ['dashboard','memory','skills','log']" in UI_HTML


def test_setmode_nexus_shows_panel_and_restores_subtab():
    start = UI_HTML.index("} else if (m === 'nexus') {")
    branch = UI_HTML[start: UI_HTML.index("} else if (m === 'forge') {", start)]
    assert "panelCol.style.display = ''" in branch
    assert "getLastSubtabForMode('nexus')" in branch
    # Nexus still drives its own dashboard tabs.
    assert "switchNexusTab(" in branch


def test_panel_visibility_helper_handles_nexus():
    assert "mode === 'nexus'" in UI_HTML
    assert "_NEXUS_PANEL_TAB_IDS.forEach" in UI_HTML


def test_switchtab_persists_nexus_subtab():
    assert "mode === 'nexus' ? 'nexus'" in PANELS_JS
