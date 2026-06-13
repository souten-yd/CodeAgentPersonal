"""Contract: Lumen Memory/Skill panels are merged into the Nexus subtab row.

UI consolidation (data/endpoints unchanged): the Memory and Skill panels are Nexus-only, so they
were relocated out of the shared side panel-col into Nexus's own subtab row (same row as
Research/Library/Evidence/Reports/Settings), keeping their inner element IDs and refresh functions.
Nexus no longer uses the shared panel-col; the panels live in nexus-col and work on desktop AND
mobile. These text-level contracts guard the wiring.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_HTML = (ROOT / "ui.html").read_text(encoding="utf-8")


def test_memory_skill_buttons_live_in_the_nexus_subtab_row():
    subtabs = UI_HTML[UI_HTML.index('<div class="nexus-subtabs">'):]
    subtabs = subtabs[: subtabs.index("</div>")]
    for name in ("memory", "skills"):
        assert f"switchNexusTab('{name}')" in subtabs
        assert f'id="nexus-btn-{name}"' in subtabs


def test_memory_skill_panels_relocated_into_nexus_body_with_inner_ids():
    # The panels now live as nexus-tab panels (data-nexus-panel), keeping their inner IDs so the
    # existing JS (refreshMemory/refreshSkills in skills_memory.js) drives them unchanged.
    assert 'id="nexus-tab-memory" data-nexus-panel="memory"' in UI_HTML
    assert 'id="nexus-tab-skills" data-nexus-panel="skills"' in UI_HTML
    assert 'id="memory-list"' in UI_HTML and 'id="skills-list"' in UI_HTML
    assert 'id="mem-category"' in UI_HTML  # add-memory form retained


def test_old_panel_col_nexus_tabs_are_gone():
    for dead in ("tab-btn-nexus-memory", "tab-btn-nexus-skills", "tab-btn-nexus-log"):
        assert dead not in UI_HTML
    assert "const _NEXUS_PANEL_TAB_IDS = [];" in UI_HTML


def test_switchnexustab_handles_memory_and_skills():
    fn = UI_HTML[UI_HTML.index("function switchNexusTab(name) {"):]
    fn = fn[: fn.index("\nfunction ")]
    assert "'memory','skills'" in fn
    assert "refreshMemory()" in fn and "refreshSkills()" in fn


def test_setmode_nexus_does_not_use_panel_col():
    start = UI_HTML.index("} else if (m === 'nexus') {")
    branch = UI_HTML[start: UI_HTML.index("} else if (m === 'forge') {", start)]
    assert "panelCol.style.display = 'none'" in branch
    # Nexus drives its own subtab row (incl. the relocated Memory/Skill).
    assert "switchNexusTab(" in branch
    assert "getLastSubtabForMode('nexus')" in branch


def test_nexus_subtabs_declared_for_persistence():
    assert "'research','library','evidence','reports','settings','memory','skills'" in UI_HTML
